# Troubleshooting

## kubectl download fails (dl.k8s.io TLS error, cdn.dl.k8s.io does not resolve)
Some home routers and DNS filters block the k8s.io download CDN. Install kubectl another way and point
the lab at it in `.env`:

```
brew install kubectl
echo 'KUBECTL_BIN=/opt/homebrew/bin/kubectl' >> .env
```
`K3D_BIN` and `HELM_BIN` work the same way. The binary is copied into `.bin/`, nothing else changes.

## kube-state-metrics stuck in ImagePullBackOff (registry.k8s.io)
Same cause: the cluster node cannot reach the registry.k8s.io CDN. `scripts/obs-install.sh` works around
it by pulling the image on the host and importing it into the cluster (`prepull_via_host`). If the host
cannot pull either, the network is the problem, not the lab.

## k3d image import: "content digest ... not found"
Docker's containerd image store saves multi-arch images in a way k3d cannot import directly. The lab
saves a single-platform tar first (`docker save --platform`). Built images are single-platform already.

## Pods crash with PermissionError on /app/core1app/*.py
Files in the build context had mode 0600. The Dockerfile now runs `chmod -R a+rX /app`; rebuild with
`make images`.

## "Permission denied" running a script
`chmod +x scripts/*.sh scripts/*.py config-repo-template/deploy.sh tests/verify.py`. Some editors and
sync tools drop the executable bit.

## A port is already in use
Change it in `.env` (see `.env.example`) and run `make down && make up`. Host ports are bound to 127.0.0.1.

## Everything is slow or pods are evicted
Docker Desktop memory is too low. Give it 8 GB or more (Settings, Resources), then `make down && make up`.

## Reading what happened
`make diag` writes a snapshot into `logs/diag-<timestamp>/`: pods, events, descriptions and logs of
unhealthy pods, Prometheus targets and rules, Alertmanager alerts, the alert sink's history, disk usage.
