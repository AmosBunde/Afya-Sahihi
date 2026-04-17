# Runbook: vLLM MedGemma operations (27B + 4B)

**When to use**: starting, stopping, or debugging the MedGemma 27B and 4B
vLLM servers on `afya-sahihi-gpu-01`. Also covers GPU sharing
verification and the start-order dependency between the two servers.

**Blast radius**: stopping either server takes inference offline. The
gateway's fail-closed response handler (issue #23) returns a refusal if
either vLLM is unreachable, so patients see "escalate to human" rather
than a wrong answer. Restart is non-destructive; vLLM has no persistent
state beyond the model weights (loaded fresh from disk).

**Start order**: 27B must start first and claim its 80% VRAM slice. The
4B unit has `After=afya-sahihi-vllm-27b.service` and its launch script
polls the 27B health endpoint for up to 180 s before proceeding. If the
27B is down, the 4B refuses to start.

## 1. Start both servers (cold boot)

```bash
sudo systemctl start afya-sahihi-vllm-27b
# Wait for 27B to finish weight loading (~120 s cold)
sudo journalctl -u afya-sahihi-vllm-27b -f --since "1 min ago"
# Look for "Application startup complete"

sudo systemctl start afya-sahihi-vllm-4b
sudo journalctl -u afya-sahihi-vllm-4b -f --since "1 min ago"
```

## 2. Verify GPU sharing

```bash
nvidia-smi
```

Expected: two `vllm` processes. The 27B process uses ~64 GB (80% of
80 GB); the 4B uses ~12 GB (15%). If the 27B is using >85%, stop both,
check `VLLM_GPU_MEMORY_UTILIZATION` in `env/vllm-27b.env` (should be
0.80), and restart in order.

## 3. Run smoke tests

```bash
VLLM_API_KEY=$(cat /etc/afya-sahihi/secrets/vllm-27b-api-key) \
    scripts/vllm/smoke_test_27b.sh

VLLM_API_KEY=$(cat /etc/afya-sahihi/secrets/vllm-4b-api-key) \
    scripts/vllm/smoke_test_4b.sh
```

Both should exit 0. The 4B smoke test additionally verifies the
`prefilter` LoRA adapter is loaded.

## 4. Restart one server without affecting the other

```bash
# Restart 4B only (does not affect 27B inference)
sudo systemctl restart afya-sahihi-vllm-4b

# Restart 27B — the 4B will lose its health-check upstream and
# eventually restart too (via its launch-script poll timeout or
# systemd BindsTo if configured). Expect ~3 min of total downtime.
sudo systemctl restart afya-sahihi-vllm-27b
```

## 5. Check DCGM GPU metrics

```bash
curl -s http://localhost:9400/metrics | grep -E "DCGM_FI_DEV_GPU_UTIL|DCGM_FI_DEV_GPU_TEMP|DCGM_FI_DEV_FB_USED"
```

These metrics feed the Grafana GPU dashboard (issue #32). Healthy
values: utilization 10–60% at steady state, temperature <80°C,
framebuffer-used matching the 80/15 split.

## 6. Debug: model loading failure

```bash
sudo journalctl -u afya-sahihi-vllm-27b --no-pager | tail -100
```

Common causes:
- "CUDA out of memory": reduce `VLLM_GPU_MEMORY_UTILIZATION` or stop
  the 4B first, then restart 27B, then 4B.
- "Connection refused" from HuggingFace: check `HF_TOKEN` in the
  credential store and internet access from the GPU host.
- "LoRA adapter not found": verify `VLLM_LORA_MODULES` paths in
  `env/vllm-4b.env` point to existing directories.

## Verify checklist

- [ ] `nvidia-smi` shows two vllm processes with expected VRAM split
- [ ] Both smoke tests exit 0
- [ ] `curl localhost:8000/health` → 200 (27B)
- [ ] `curl localhost:8001/health` → 200 (4B)
- [ ] `curl localhost:9400/metrics` → DCGM metrics present
- [ ] Grafana "GPU" dashboard shows live data
