# Runbook: GpuMemoryPressure

**Alert:** `GpuMemoryPressure` · **Severity:** warning · **Fires when:** GPU memory used / (used + free) > 0.92 for 10m.

## Impact

vLLM's paged-attention scheduler will start rejecting new requests once the KV cache cannot grow. Clinicians see 429s and retries pile up in the Redis rate limiter.

## Triage

1. **GPU** dashboard → which GPU, which host. Usually `afya-sahihi-gpu-01` GPU 0 (27B) or GPU 1 (4B).
2. Check the **LLM** dashboard — has tokens-per-second dropped sharply (saturation) or stayed stable (slow leak)?
3. `ssh afya-sahihi-gpu-01.internal` then `nvidia-smi` to confirm DCGM's numbers; occasionally DCGM's FB metric is stale vs. `nvidia-smi`.

## Containment

- **Saturation** (tokens/sec dropped): traffic spike. Scale down `max_num_seqs` in the vLLM systemd unit via the observability.env override, then `systemctl reload afya-sahihi-vllm-27b`.
- **Leak** (slow creep over hours): restart the vLLM process to reclaim paged attention memory. `systemctl restart afya-sahihi-vllm-27b`. Expect a 30s drain.
- If both GPUs on the same host are pressured at once, page the GPU on-call — hardware investigation.

## Verify

- GPU memory < 85% sustained.
- Gateway RED panel shows 429s returning to baseline.
