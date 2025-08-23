#!/usr/bin/env bash
set -euo pipefail

# Inputs via environment variables
# BACKEND_VERSION: e.g. 1.3.2

if [[ -z "${BACKEND_VERSION:-}" ]]; then
  echo "BACKEND_VERSION must be set" >&2
  exit 1
fi

DIR="kubernetes/party-battle/backend/versions/v${BACKEND_VERSION}"

if [[ -d "${DIR}" ]]; then
  git rm -r "${DIR}"
else
  echo "Directory ${DIR} does not exist; nothing to remove."
fi

KFILE="kubernetes/party-battle/backend/kustomization.yaml"
LINE="  - versions/v${BACKEND_VERSION}/"
if [[ -f "${KFILE}" ]]; then
  # portable in-place sed (Linux CI environment supports -i)
  sed -i "\|${LINE}|d" "${KFILE}"
fi

echo "Removed backend version manifests for v${BACKEND_VERSION}"


