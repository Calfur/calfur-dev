# Repository-managed workload security

These controls belong to the manifests and deployment workflow in this repository.
The PR does not change the live cluster. The existing deployment workflow applies
these manifests when the PR is merged to `master`.

## Pod restrictions

Every long-running container enforces a numeric non-root user, `RuntimeDefault`
seccomp, no privilege escalation, capability drops, and CPU/memory requests and
limits. Applications and monitoring do not mount Kubernetes service account tokens.
Traefik retains its dedicated API credential because its CRD provider needs it.

Nginx sites run as UID/GID 101, invoke Nginx directly, and use bounded `emptyDir`
mounts for `/var/cache/nginx`, `/var/run`, and `/tmp`. They retain only
`NET_BIND_SERVICE` because the existing image configurations listen on port 80.
Next.js sites run as UID/GID 1001 with writable `/app/.next/cache` and `/tmp`.
Bun apps use UID/GID 1000. Monitoring uses its image's service users (Prometheus
65534, Grafana 472), with writable data and temporary mounts.

The resource bounds are starting budgets, not values derived from production load.
Static sites request 25m CPU / 32Mi memory and limit memory to 128Mi. Most dynamic
apps request 25m / 128Mi and limit memory to 512Mi; Next.js apps use 768Mi.
Traefik requests 100m / 128Mi and limits memory to 512Mi. Each monitoring container
requests 100m / 128Mi and limits memory to 1Gi. All containers limit CPU, and
writable application volumes have size bounds. Review OOMs/throttling during rollout.

Two compatibility exceptions are explicit:

- Killer keeps a writable image filesystem: the pinned image writes `game.json`
  relative to `/app`. Its non-root user, seccomp, capability drops, token removal,
  and resource bounds still apply. Moving game state to a dedicated volume requires
  an application/image change outside this repository.
- Traefik's certificate initializer runs briefly as UID 0 with only `CHOWN` and
  `DAC_OVERRIDE`, on a read-only image filesystem. It changes ownership of `/data`
  and the existing `/data/acme.json` to UID/GID 65532 without replacing certificate
  contents or changing their modes. The controller then runs as that non-root user.
  The traversal capability supports repeated rollouts when the directory is mode 0700.

Grafana and Prometheus data remain ephemeral, as in the previous manifests.
`emptyDir` permits writes with the image filesystem read-only; it does not add
persistence. Export any dashboards or state that must survive a pod replacement.

## Ingress and monitoring

Traefik is pinned to `v3.7.13`, with the matching upstream CRDs vendored in
`traefik/external/kubernetes-crd-definition-v1.yml`. Its insecure API is disabled.
The provider watches only `default` and disables discovery of cluster-scoped
resources. A Role/RoleBinding grants read access to Services, Secrets, ConfigMaps,
EndpointSlices, and Traefik CRDs in that namespace. It grants no cluster-wide
permissions or writes. Namespace scoping still includes Secrets of other apps in
`default`; separate namespaces would be required for further credential separation.

The deployment workflow waits for the new controller, then explicitly removes the
old `traefik-ingress-controller` ClusterRoleBinding and ClusterRole. Applying new
YAML alone would leave those historical cluster-wide grants active.

Grafana is pinned to `13.2.3` and requires login; anonymous Viewer access is disabled.
The existing `grafana-admin-credentials` Secret remains its bootstrap credential.

## Network policies

The policies select pods labeled `app.kubernetes.io/managed-by: calfur-dev` in
`default`, including dynamically generated Party Battle versions. Unrelated pods
are not selected. The deployment workflow applies this package explicitly.

| Source | Destination | Allowed traffic |
| --- | --- | --- |
| Public clients | Traefik | TCP 8000 / 4443 (Service ports 80 / 443) |
| Traefik | Repository web/API pods | Named TCP ports `web` / `api` |
| Grafana | Prometheus | TCP 9090 |
| All repository pods | CoreDNS in `kube-system` | UDP/TCP 53 |
| Repository pods except Prometheus | Public addresses | TCP 80 / 443 |
| Traefik | Kubernetes API | TCP 443 / 6443 |
| Arctic Kälte homepage | Public SMTP relay | TCP 587 |

Public egress excludes private, loopback, link-local/metadata, and multicast ranges
for IPv4 and IPv6. Applications cannot connect directly to each other's pod ports,
Prometheus, or management ports. Traefik needs a wider 443/6443 egress exception
because the API Service and endpoint can be evaluated before or after Service DNAT.
NetworkPolicy is an L3/L4 control: public egress is not a hostname allowlist and
access to public websites remains possible. Enforcement depends on the cluster's
network policy controller; this PR does not configure the host or CNI.

Prometheus currently uses its image's default self-scrape configuration. Additional
internal scrape targets, private external dependencies, or new inter-app calls need
explicit policy allowances before they are introduced.

## Validation and rollout

With Kustomize 5.8.1, kubeconform 0.7.0, Python 3.12 and `PyYAML==6.0.3` available:

```sh
python scripts/validate_manifests.py
```

This renders every Kustomization, validates built-in Kubernetes 1.36 schemas and
Traefik resources against the vendored CRDs, checks restrictions and routing/network
allowances, and exercises the backend generator in a temporary directory. It never
contacts the cluster. CI verifies checksums for its pinned tool downloads and is a
prerequisite for the deployment job.

After merge, verify deployment rollouts, website HTTPS and WebSockets, Grafana login
and datasource access, Arctic contact mail, and Traefik certificate renewal. Confirm
application-to-Prometheus connections and management-port connections are blocked.
The local checks model policy intent; they do not prove live CNI enforcement or
container startup. Containers were not run locally because Docker was unavailable.

Node firewall rules, k3s Secrets encryption, API audit logging, and node service
configuration are outside this repository change.

Upstream references: [Traefik release](https://github.com/traefik/traefik/releases/tag/v3.7.13),
[Traefik migration guidance](https://doc.traefik.io/traefik/migrate/v3/),
[Grafana release](https://github.com/grafana/grafana/releases/tag/v13.2.3),
[Kubernetes pod restrictions](https://kubernetes.io/docs/concepts/security/pod-security-standards/),
[NetworkPolicy semantics](https://kubernetes.io/docs/concepts/services-networking/network-policies/).
