# ADR-0005: k3s with systemd watcher over full Kubernetes

**Status:** Accepted
**Date:** 2026-04-16
**Deciders:** Ezra O'Marley

## Context

Afya Gemma v1 ran directly on GCE VMs with a custom systemd watcher that polled a git repository and applied changes. This worked well for a single-service deployment but started to strain as we added the retrieval service, the conformal service, the eval runner, and the observability stack.

Full Kubernetes (EKS, GKE, kubeadm) solves the orchestration problem but brings operational weight that is not justified by our scale. Our entire workload fits on three nodes. An AKU infrastructure team of three people should not spend any portion of their day reasoning about kube-scheduler, cloud-controller-manager, or cluster autoscaling.

## Decision

The orchestration plane is **k3s**, Rancher's lightweight Kubernetes distribution. A single k3s server runs on the control node. Worker nodes join the cluster. The GPU node (running vLLM) runs outside k3s on bare metal, managed by systemd.

GitOps is handled by the existing **systemd git-polling watcher** ported from v1. It polls the deployment manifests repo every 60 seconds, `kubectl apply -f` on diff, and logs to journald. There is no Flux, no ArgoCD.

Container images come from self-hosted Harbor. Secrets via Sealed Secrets.

## Consequences

**Positive**

- k3s has the same API surface as Kubernetes but runs as a single binary and requires roughly 5 percent of the memory. The control plane fits comfortably alongside workloads.
- Our existing systemd watcher is battle-tested. Porting it to `kubectl apply` is a 50-line change.
- When a developer SSHs into a node, `systemctl status k3s` and `journalctl -u k3s` tell them everything they need.
- GPU workloads bypass k3s entirely. vLLM on bare metal has no container runtime overhead and no device plugin complexity.

**Negative**

- We give up multi-cluster features, cloud-integrated load balancers, and cluster federation. We do not need any of them.
- The systemd watcher is not a sophisticated GitOps tool. It has no PR-based promotion, no drift detection beyond "does the cluster match the repo." For our scale this is sufficient. If we outgrow it, we can adopt Flux without changing manifests.
- Upgrades are manual. k3s releases are pinned per quarter.

**Neutral**

- The observability stack (Prometheus, Grafana, Loki, Tempo) runs inside k3s. It scrapes the GPU node via Node Exporter and DCGM Exporter over the management network.

## Cluster topology

| Node | Role | Workloads |
|------|------|-----------|
| afya-sahihi-ctrl-01 | k3s server, ingress | Traefik, frontend, gateway |
| afya-sahihi-work-01 | k3s worker | Retrieval, conformal, ingestion, eval |
| afya-sahihi-work-02 | k3s worker | Audit, AL scheduler, Streamlit, observability |
| afya-sahihi-data-01 | bare metal Postgres | PG 16, MinIO, Redis |
| afya-sahihi-gpu-01 | bare metal vLLM | MedGemma 27B + 4B |
| afya-sahihi-deploy-01 | systemd watcher host | Git polling, kubectl, alerting sidecar |

Networking: single VLAN, private. Access via bastion with SSH key plus hardware token.

## Alternatives considered

- **Full kubeadm-bootstrapped Kubernetes**: rejected on operational weight.
- **Docker Compose**: we already use this for dev. It does not scale to multi-node without switching to Swarm, which is end-of-life-ish.
- **Nomad**: strong alternative. We chose k3s for ecosystem depth (Traefik, Sealed Secrets, exporters).
- **Pure systemd across all nodes**: tempting for the smallest deployment, but we lose declarative deployment and pod-level isolation.

## Compliance and references

- k3s version pinned to v1.33.x (current stable as of April 2026)
- Manifests in `deploy/k3s/`
- systemd units in `deploy/systemd/`
- Related: ADR-0001 (GPU node is bare metal), observability stack in main README
