# calfur-dev

The repository responsible to deploy projects on my server

## Website

https://calfur.dev

## How to preper a new server

The setup is based on this guide: https://doc.traefik.io/traefik/user-guides/crd-acme/#traefik-crd-lets-encrypt.

### Install K3s

https://docs.k3s.io/quick-start

curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server --disable traefik" sh -s -

### Run the GitHub Action

Make sure the secrets SERVER_IP, SERVER_USER and SSH_PRIVATE_KEY are configured correctly.

### Enable temporary port forwarding to create the first https certificate

kubectl port-forward --address 0.0.0.0 service/traefik 443:4443 -n default

### How to uninstall K3s

https://docs.k3s.io/installation/uninstall

/usr/local/bin/k3s-uninstall.sh
