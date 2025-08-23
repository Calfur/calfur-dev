#!/usr/bin/env bash
set -euo pipefail

# Inputs via environment variables
# BACKEND_VERSION: e.g. 1.3.2
# IMAGE_VERSION: image tag/sha for ghcr.io/thirty-degrees/backend-party-battle

if [[ -z "${BACKEND_VERSION:-}" || -z "${IMAGE_VERSION:-}" ]]; then
  echo "BACKEND_VERSION and IMAGE_VERSION must be set" >&2
  exit 1
fi

DIR="kubernetes/party-battle/backend/versions/v${BACKEND_VERSION}"
SVC="party-battle-backend-v$(echo "${BACKEND_VERSION}" | tr '.' '-')"

mkdir -p "${DIR}"

cat > "${DIR}/kustomization.yaml" <<EOF
resources:
  - 01-service.yml
  - 02-deployment.yml
  - 03-ingress.yml
EOF

cat > "${DIR}/01-service.yml" <<EOF
apiVersion: v1
kind: Service
metadata:
  namespace: default
  name: ${SVC}

spec:
  ports:
    - protocol: TCP
      name: api
      port: 80
      targetPort: 2567
  selector:
    app: ${SVC}
EOF

cat > "${DIR}/02-deployment.yml" <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  namespace: default
  name: ${SVC}
  labels:
    app: ${SVC}

spec:
  replicas: 1
  selector:
    matchLabels:
      app: ${SVC}
  template:
    metadata:
      labels:
        app: ${SVC}
    spec:
      containers:
        - name: party-battle-backend
          image: ghcr.io/thirty-degrees/backend-party-battle:${IMAGE_VERSION}
          ports:
            - name: api
              containerPort: 2567
      imagePullSecrets:
        - name: ghcr-secret
EOF

TMP_FILE=$(mktemp)
cat > "${TMP_FILE}" <<'EOF'
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  namespace: default
  name: __INGRESS_NAME__
spec:
  entryPoints:
    - websecure
  routes:
    - match: Host(`party-battle.thirty-degrees.ch`) && PathPrefix(`/api/v__BV__`)
      kind: Rule
      priority: 10
      services:
        - name: __SVC__
          port: 80
  tls:
    certResolver: myresolver
EOF
ING="ingressroute-${SVC}"
sed "s|__INGRESS_NAME__|${ING}|g; s|__SVC__|${SVC}|g; s|__BV__|${BACKEND_VERSION}|g" "${TMP_FILE}" > "${DIR}/03-ingress.yml"
rm -f "${TMP_FILE}"

# Ensure backend kustomization references this version
KFILE="kubernetes/party-battle/backend/kustomization.yaml"
LINE="  - versions/v${BACKEND_VERSION}/"
if ! grep -qxF "${LINE}" "${KFILE}"; then
  echo "${LINE}" >> "${KFILE}"
fi

echo "Generated backend version manifests in ${DIR}"
