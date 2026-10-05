# Repository instructions

This repository deploys Kubernetes workloads to the K3s server `calfur-001`.
Regular deployments run through `.github/workflows/deploy.yml`.

## Server access

- Connect to `calfur-001` over SSH only when the user explicitly requests server
  access for the current task. This includes read-only checks, SCP, SFTP and port
  forwarding. General repository work does not authorize server access.
- Commands that modify the server or live cluster require explicit user
  authorization for those changes. Permission to inspect does not permit writes.

## Kubernetes

- Render manifests locally with `kubectl kustomize kubernetes`. Do not assume a
  local kubectl context points to `calfur-001`; run cluster commands over SSH only
  within the authorized scope.
