# calfur-dev
The repository responsible to deploy my projects on my server

## Website
https://calfur.dev

## How to preper a new server

### Install K3s

curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server --disable traefik" sh -s -

### Modify K3s settings (add lines)

/etc/rancher/k3s/config.yaml

```yaml
write-kubeconfig-mode: "0666"
tls-san:
  - "calfur.dev"
  - "*.calfur.dev"
cluster-init: true
```


### How to uninstall K3s
https://docs.k3s.io/installation/uninstall

/usr/local/bin/k3s-uninstall.sh
