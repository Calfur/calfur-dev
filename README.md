# calfur-dev
The repository responsible to deploy my projects on my server

## Website
https://calfur.dev

## How to preper a new server

### Install K3s

curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server --disable traefik" sh -s -

### Enable temporary port forwarding to create the first https certificate

kubectl port-forward --address 0.0.0.0 service/traefik 443:4443 -n default

### How to uninstall K3s
https://docs.k3s.io/installation/uninstall

/usr/local/bin/k3s-uninstall.sh
