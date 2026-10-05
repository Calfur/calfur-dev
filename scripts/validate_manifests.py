#!/usr/bin/env python3
"""Render and check manifests locally; never contact or mutate a cluster."""
import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.request import urlopen

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANAGED = {"app.kubernetes.io/managed-by": "calfur-dev"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def build(directory):
    result = subprocess.run(
        ["kustomize", "build", str(directory)], check=True, capture_output=True, text=True
    )
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def matches(selector, labels):
    if any(labels.get(k) != v for k, v in selector.get("matchLabels", {}).items()):
        return False
    for expression in selector.get("matchExpressions", []):
        key, op = expression["key"], expression["operator"]
        values = expression.get("values", [])
        if op == "In" and labels.get(key) not in values:
            return False
        if op == "NotIn" and labels.get(key) in values:
            return False
        if op == "Exists" and key not in labels:
            return False
        if op == "DoesNotExist" and key in labels:
            return False
    return True


def peer_matches(peer, endpoint):
    if "ipBlock" in peer:
        address = ipaddress.ip_address(endpoint["ip"])
        block = peer["ipBlock"]
        return address in ipaddress.ip_network(block["cidr"]) and not any(
            address in ipaddress.ip_network(cidr) for cidr in block.get("except", [])
        )
    if "namespace" not in endpoint:
        return False
    if "namespaceSelector" in peer:
        if not matches(peer["namespaceSelector"], endpoint["namespaceLabels"]):
            return False
    elif endpoint["namespace"] != "default":
        return False
    return matches(peer.get("podSelector", {}), endpoint["labels"])


def allowed(policies, direction, selected, remote, destination, port, protocol="TCP"):
    relevant = [p["spec"] for p in policies if direction in p["spec"]["policyTypes"]
                and matches(p["spec"]["podSelector"], selected["labels"])]
    if not relevant:
        return True
    peer_key = "from" if direction == "Ingress" else "to"
    for policy in relevant:
        for rule in policy.get(direction.lower(), []):
            if peer_key in rule and not any(peer_matches(p, remote) for p in rule[peer_key]):
                continue
            for entry in rule.get("ports", [{"protocol": protocol, "port": port}]):
                number = entry.get("port", port)
                if isinstance(number, str):
                    number = destination.get("ports", {}).get(number)
                if entry.get("protocol", "TCP") == protocol and number is not None:
                    if number <= port <= entry.get("endPort", number):
                        return True
    return False


def endpoint(spec, labels, index):
    return {"labels": labels, "namespace": "default",
            "namespaceLabels": {"kubernetes.io/metadata.name": "default"},
            "ip": f"10.42.0.{index + 2}",
            "ports": {p["name"]: p["containerPort"] for c in spec["containers"]
                      for p in c.get("ports", [])}}


def validate_workload(deployment):
    name = deployment["metadata"]["name"]
    pod = deployment["spec"]["template"]
    require(matches({"matchLabels": MANAGED}, pod["metadata"]["labels"]), f"{name}: policy label missing")
    spec = pod["spec"]
    sc = spec.get("securityContext", {})
    require(sc.get("runAsNonRoot") is True and sc.get("runAsUser", 0) > 0, f"{name}: non-root not enforced")
    require(sc.get("seccompProfile", {}).get("type") == "RuntimeDefault", f"{name}: seccomp missing")
    require(spec.get("automountServiceAccountToken") is (name == "traefik"), f"{name}: API token policy incorrect")
    require(not any(spec.get(k) for k in ("hostNetwork", "hostPID", "hostIPC")), f"{name}: host isolation missing")
    for container in spec["containers"] + spec.get("initContainers", []):
        cs = container.get("securityContext", {})
        require(cs.get("allowPrivilegeEscalation") is False and not cs.get("privileged"), f"{name}: escalation permitted")
        require(cs.get("capabilities", {}).get("drop") == ["ALL"], f"{name}: capabilities not dropped")
        init = name == "traefik" and container["name"] == "certificate-permissions"
        if not init:
            require(set(cs.get("capabilities", {}).get("add", [])) <= {"NET_BIND_SERVICE"}, f"{name}: excessive capabilities")
        require(cs.get("readOnlyRootFilesystem") is (name != "killer"), f"{name}: unexpected writable image")
        for bound in ("requests", "limits"):
            require({"cpu", "memory"} <= container.get("resources", {}).get(bound, {}).keys(), f"{name}: resource {bound} missing")


def main():
    documents = []
    for kustomization in sorted((ROOT / "kubernetes").rglob("kustomization.yaml")):
        rendered = build(kustomization.parent)
        # Render nested packages too, but validate resources only once.
        if kustomization.parent.parent == ROOT / "kubernetes":
            documents.extend(rendered)
    with tempfile.TemporaryDirectory(prefix="calfur-validation-") as temporary:
        temp = Path(temporary)
        schemas = temp / "schemas"
        schemas.mkdir()
        # CRDs are absent from kubeconform's default schema registry. Use the
        # same Kubernetes release's official API schema instead of skipping them.
        url = "https://raw.githubusercontent.com/kubernetes/kubernetes/v1.36.0/api/openapi-spec/v3/apis__apiextensions.k8s.io__v1_openapi.json"
        with urlopen(url, timeout=30) as response:
            official = json.load(response)
        crd_schema = {
            "$ref": "#/components/schemas/io.k8s.apiextensions-apiserver.pkg.apis.apiextensions.v1.CustomResourceDefinition",
            "components": official["components"],
        }
        (schemas / "customresourcedefinition_v1.json").write_text(json.dumps(crd_schema))
        for doc in documents:
            if doc["kind"] == "CustomResourceDefinition":
                for version in doc["spec"]["versions"]:
                    filename = f'{doc["spec"]["names"]["kind"].lower()}_{version["name"]}.json'
                    (schemas / filename).write_text(json.dumps(version["schema"]["openAPIV3Schema"]))
        # The generator must preserve hardening and participate in the shared policies.
        shutil.copytree(ROOT / "kubernetes/party-battle", temp / "kubernetes/party-battle")
        subprocess.run(["bash", str(ROOT / ".github/scripts/add_party_battle_backend_version.sh")],
                       cwd=temp, env={**os.environ, "BACKEND_VERSION": "9.8.7", "IMAGE_VERSION": "test-sha"}, check=True)
        generated = build(temp / "kubernetes/party-battle/backend/versions/v9.8.7")
        validate_workload(next(d for d in generated if d["kind"] == "Deployment"))
        documents.extend(generated)
        manifest = temp / "rendered.yml"
        manifest.write_text(yaml.safe_dump_all(documents, sort_keys=False))
        subprocess.run([
            "kubeconform", "-strict", "-summary", "-kubernetes-version", "1.36.0",
            "-schema-location", "default", "-schema-location",
            str(schemas / "{{.ResourceKind}}_{{.ResourceAPIVersion}}.json"), str(manifest)
        ], check=True)

    deployments = {d["metadata"]["name"]: d for d in documents if d["kind"] == "Deployment"}
    for deployment in deployments.values():
        validate_workload(deployment)
    pods = {name: endpoint(d["spec"]["template"]["spec"], d["spec"]["template"]["metadata"]["labels"], index)
            for index, (name, d) in enumerate(deployments.items())}
    policies = [d for d in documents if d["kind"] == "NetworkPolicy"]
    traefik, grafana, prometheus = (pods[n] for n in ("traefik", "grafana", "prometheus"))
    services = {d["metadata"]["name"]: d for d in documents if d["kind"] == "Service"}

    def can_connect(source, destination, port, protocol="TCP"):
        return (allowed(policies, "Egress", source, destination, destination, port, protocol)
                and allowed(policies, "Ingress", destination, source, destination, port, protocol))

    # Resolve every declared ingress through Service -> Pod -> named/numeric port.
    for route in (d for d in documents if d["kind"] == "IngressRoute"):
        for rule in route["spec"]["routes"]:
            for target in rule.get("services", []):
                service = services[target["name"]]["spec"]
                ports = [p for p in service["ports"] if p["port"] == target["port"]]
                require(len(ports) == 1, f'{target["name"]}: route port missing')
                port = ports[0].get("targetPort", ports[0]["port"])
                destinations = [p for p in pods.values() if matches({"matchLabels": service["selector"]}, p["labels"])]
                require(destinations, f'{target["name"]}: Service selects no pod')
                for destination in destinations:
                    number = destination["ports"].get(port) if isinstance(port, str) else port
                    require(can_connect(traefik, destination, number), f'{target["name"]}: ingress blocked')
    require(can_connect(grafana, prometheus, 9090), "Grafana cannot query Prometheus")
    for name, source in pods.items():
        if name in {"traefik", "prometheus", "grafana"}:
            continue
        require(not can_connect(source, prometheus, 9090), f"{name}: Prometheus exposed")
        require(not can_connect(source, traefik, 8080), f"{name}: Traefik API exposed")
        for other, destination in pods.items():
            if name != other and other != "traefik":
                for port in destination["ports"].values():
                    require(not can_connect(source, destination, port), f"{name}: lateral access to {other}")
        for ip in ("10.43.0.1", "169.254.169.254", "192.168.1.1", "fd00::1", "fe80::1"):
            destination = {"ip": ip}
            require(not allowed(policies, "Egress", source, destination, destination, 443), f"{name}: private/metadata access")
        for ip in ("1.1.1.1", "2606:4700:4700::1111"):
            external = {"ip": ip}
            require(allowed(policies, "Egress", source, external, external, 443), f"{name}: external HTTPS blocked")
            for port in (6443, 10250, 8080):
                require(not allowed(policies, "Egress", source, external, external, port), f"{name}: management egress allowed")
    dns = {"ip": "10.42.1.1", "namespace": "kube-system", "namespaceLabels": {"kubernetes.io/metadata.name": "kube-system"},
           "labels": {"k8s-app": "kube-dns"}}
    for name, pod in pods.items():
        for protocol in ("TCP", "UDP"):
            require(allowed(policies, "Egress", pod, dns, dns, 53, protocol), f"{name}: DNS blocked")
    external = {"ip": "1.1.1.1"}
    for port in (8000, 4443):
        require(allowed(policies, "Ingress", traefik, external, traefik, port), "Public ingress blocked")
    for ip, port in (("10.43.0.1", 443), ("10.42.0.1", 6443)):
        api = {"ip": ip}
        require(allowed(policies, "Egress", traefik, api, api, port), "Traefik API discovery blocked")
    require(allowed(policies, "Egress", pods["arctic-kaelte-homepage"], external, external, 587), "SMTP blocked")
    require(not allowed(policies, "Egress", pods["homepage"], external, external, 587), "SMTP exception too broad")
    require(not any(d["kind"] in {"ClusterRole", "ClusterRoleBinding"} for d in documents), "Cluster-wide RBAC returned")
    args = deployments["traefik"]["spec"]["template"]["spec"]["containers"][0]["args"]
    require(not any(arg.startswith("--api.insecure") for arg in args), "Insecure Traefik API enabled")
    require("--providers.kubernetescrd.namespaces=default" in args and "--providers.kubernetescrd.disableclusterscoperesources=true" in args,
            "Traefik watches beyond its Role scope")
    print(f"Validated {len(deployments)} deployments (including a generated version), all ingress routes, and network isolation")


if __name__ == "__main__":
    main()
