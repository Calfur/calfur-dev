# calfur-dev

The repository responsible to deploy projects on my server

## Website

https://calfur.dev

[![Deploy to Kubernetes (calfur-001)](https://github.com/Calfur/calfur-dev/actions/workflows/deploy.yml/badge.svg)](https://github.com/Calfur/calfur-dev/actions/workflows/deploy.yml)

## How to prepare a new server

### SSH

Inspect current settings with:

- ssh: `sudo sshd -T`
- firewall: `sudo ufw status verbose`

Backup SSH settings with:

- `sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak`

Update settings with:

- Disable PasswordAuthentication
  - `sudo sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config`
  - `sudo systemctl reload ssh`
- Change port (don't use 22)
  - `sudo sed -i 's/^#\?Port .*/Port 22/' /etc/ssh/sshd_config`
  - `sudo systemctl reload ssh`
  - `sudo ufw allow 22/tcp`
  - `sudo ufw delete allow 22/tcp`
  - `sudo ufw reload`

Maybe a restart of the server helps in case of something going wrong.

### Kubernetes

The https certificate setup is based on this guide: https://doc.traefik.io/traefik/user-guides/crd-acme/#traefik-crd-lets-encrypt.

#### Install K3s

https://docs.k3s.io/quick-start

curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server --disable traefik" sh -s -

#### Run the GitHub Action

Make sure the secrets SERVER_IP, SERVER_USER and SSH_PRIVATE_KEY are configured correctly.

#### Enable temporary port forwarding to create the first https certificate

kubectl port-forward --address 0.0.0.0 service/traefik 443:443 -n default

#### How to uninstall K3s

https://docs.k3s.io/installation/uninstall

/usr/local/bin/k3s-uninstall.sh

## Current server calfur-001

### Connect to server

-   SSH with private key & password
-   Termius or Terminal with credentials from KeePass

### Useful commands

- docker build -t nginx-calfur-dev .
- docker stop nginx-proxy
- docker rm nginx-proxy
- docker run -d --name nginx-proxy --network webnet -p 443:443 nginx-calfur-dev

#### Debug:

- kubectl get pods --all-namespaces
- kubectl logs traefik-b5965ccd-wdklg
- cd ../letsencrypt/
- kubectl delete pods --all
- kubectl logs -n default deployment/traefik --tail=50
- kubectl get ingressroute,ingress,svc,deploy,pod -n default | cat
- kubectl get all,ingressroute,middleware -l app.kubernetes.io/part-of=party-battle -o wide
