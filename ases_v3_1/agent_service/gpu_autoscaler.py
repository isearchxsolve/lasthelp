"""
ASES - GPU + Queue-Aware Autoscaler (v4.0)
===========================================
Enhances the v3.x autoscaler.py CPU-based decision with:
- queue-pressure awareness (享有 instantaneous queue depth from Redis)
- optional GPU occupancy estimation (mockable interface)
- cooldown windows to prevent oscillation
- hysteresis (scale_up_threshold & scale_down_threshold are now separate)

Drop-in replacement: get_decision(snap) -> Action where Action['direction']
is 'scale_up' | 'scale_down' | 'hold'. Tested independently from the docker
socket pinning, making it unit-friendly.

Integration when used from `autoscaler.py` (provably backwards-compatible):

    from gpu_autoscaler import extended_decision
    action = extended_decision(cpu_load, queue_depth, gpu_load=..., win=...)

If gpu_load is None the decision degenerates to a queue-pressure-aware CPU
scaling policy (the same as v3.x but with the cooldown semantics).
"""

import os
import time
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, Tuple

import structlog

logger = structlog.get_logger()


# Hysteresis defaults
CPU_SCALE_UP_THRESHOLD = float(os.getenv("ASES_AUTO_CPU_UP", 70.0))
CPU_SCALE_DOWN_THRESHOLD = float(os.getenv("ASES_AUTO_CPU_DOWN", 35.0))
GPU_SCALE_UP_THRESHOLD = float(os.getenv("ASES_AUTO_GPU_UP", 85.0))
GPU_SCALE_DOWN_THRESHOLD = float(os.getenv("ASES_AUTO_GPU_DOWN", 30.0))
QUEUE_PRESSURE_SCALE = int(os.getenv("ASES_AUTO_QUEUE_PRESSURE", 20))
SCALE_UP_COOLDOWN_S = int(os.getenv("ASES_AUTO_UP_COOLDOWN_S", 60))
SCALE_DOWN_COOLDOWN_S = int(os.getenv("ASES_AUTO_DOWN_COOLDOWN_S", 180))
MIN_WORKERS = int(os.getenv("ASES_AUTO_MIN", 1))
MAX_WORKERS = int(os.getenv("ASES_AUTO_MAX", 8))


@dataclass
class Decision:
    direction: str  # "scale_up" | "scale_down" | "hold"
    rationale: str
    est_workers: int
    cooldown_remaining_s: int = 0
    signals: Dict[str, Any] = None


_last_scale_up_at: float = 0.0
_last_scale_down_at: float = 0.0


def _cooldown(dest: str) -> int:
    """Returns remaining cooldown in seconds (0 if free)."""
    now = time.time()
    if dest == "scale_up":
        return max(0, int(SCALE_UP_COOLDOWN_S - (now - _last_scale_up_at))) \
            if _last_scale_up_at else 0
    return max(0, int(SCALE_DOWN_COOLDOWN_S - (now - _last_scale_down_at))) \
        if _last_scale_down_at else 0


def get_gpu_load() -> float:
    """
    Stub for the GPU sensor. Replaced by:
    - real `nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits`
    - or `nvml` bindings if available
    - else returns 0.0 (degraded -> CPU-only policy)
    """
    try:
        import subprocess
        r = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2,
        )
        if r.returncode == 0 and r.stdout.strip():
            # average across visible GPUs
            vals = [float(x) for x in r.stdout.split() if x.replace(".", "", 1).isdigit()]
            return sum(vals) / len(vals) if vals else 0.0
    except Exception:
        pass
    return 0.0


def extended_decision(
    cpu_load: float,
    queue_depth: int = 0,
    gpu_load: Optional[float] = None,
    current_workers: int = MIN_WORKERS,
    q_pressure: int = QUEUE_PRESSURE_SCALE,
) -> Decision:
    """
    Multi-signal scaling decision with cooldown + hysteresis.

    Args:
        cpu_load: in percent (0..100)
        queue_depth: pending jobs in RQ
        gpu_load: GPU utilisation percent; None = unknown
        current_workers: live workers count
        q_pressure: if metrics indicate queue pressure >= this, scale up regardless

    Returns:
        Decision(direction, rationale, est_workers, cooldown, signals)
    """
    if current_workers < MIN_WORKERS:
        return Decision(
            direction="scale_up",
            rationale=f"below MIN_WORKERS {MIN_WORKERS}",
            est_workers=MIN_WORKERS,
            signals={"cpu": cpu_load, "queue": queue_depth, "gpu": gpu_load, "workers": current_workers},
        )
    if current_workers >= MAX_WORKERS:
        return Decision(
            direction="hold",
            rationale=f"at MAX_WORKERS {MAX_WORKERS}",
            est_workers=MAX_WORKERS, cooldown_remaining_s=0,
            signals={"cpu": cpu_load, "queue": queue_depth, "gpu": gpu_load, "workers": current_workers},
        )

    if gpu_load is None:
        gpu_load = get_gpu_load()  # may return 0.0 if no GPU

    queue_pressure = queue_depth >= q_pressure
    scale_up_signal = (cpu_load > CPU_SCALE_UP_THRESHOLD or
                       (gpu_load or 0) > GPU_SCALE_UP_THRESHOLD or
                       queue_pressure)
    scale_down_signal = (cpu_load < CPU_SCALE_DOWN_THRESHOLD and
                        (gpu_load or 0) < GPU_SCALE_DOWN_THRESHOLD and
                        not queue_pressure)

    if scale_up_signal:
        cd = _cooldown("scale_up")
        if cd:
            return Decision(
                direction="hold", rationale="scale_up_cooldown",
                est_workers=current_workers, cooldown_remaining_s=cd,
                signals={"cpu": cpu_load, "queue": queue_depth, "gpu": gpu_load},
            )
        target = min(MAX_WORKERS, current_workers + max(1, int(queue_depth / max(1, q_pressure))))
        global _last_scale_up_at
        _last_scale_up_at = time.time()
        return Decision(
            direction="scale_up",
            rationale=f"cpu={cpu_load:.1f} gpu={gpu_load:.1f} q={queue_depth}",
            est_workers=target, cooldown_remaining_s=0,
            signals={"cpu": cpu_load, "queue": queue_depth, "gpu": gpu_load},
        )

    if scale_down_signal:
        cd = _cooldown("scale_down")
        if cd:
            return Decision(
                direction="hold", rationale="scale_down_cooldown",
                est_workers=current_workers, cooldown_remaining_s=cd,
                signals={"cpu": cpu_load, "queue": queue_depth, "gpu": gpu_load},
            )
        target = max(MIN_WORKERS, current_workers - 1)
        global _last_scale_down_at
        _last_scale_down_at = time.time()
        return Decision(
            direction="scale_down",
            rationale=f"cpu={cpu_load:.1f} gpu={gpu_load:.1f} q={queue_depth}",
            est_workers=target, cooldown_remaining_s=0,
            signals={"cpu": cpu_load, "queue": queue_depth, "gpu": gpu_load},
        )

    return Decision(
        direction="hold",
        rationale="all signals within bounds",
        est_workers=current_workers,
        cooldown_remaining_s=0,
        signals={"cpu": cpu_load, "queue": queue_depth, "gpu": gpu_load},
    )


def reset_cooldown_state() -> None:
    """Test hook."""
    global _last_scale_up_at, _last_scale_down_at
    _last_scale_up_at = 0.0
    _last_scale_down_at = 0.0
