"""GPU/CPU capability detection, benchmarking and device policy.

The pipeline is GPU-first for tensor workloads (variational inference,
posterior predictive sampling, Bayesian regime head) but keeps pandas/HMM/
EGARCH/EBM on CPU. ``collect_hardware_report`` never assumes a device is
faster: ``benchmark_devices`` measures it.
"""

from __future__ import annotations

import json
import platform
import sys
import time
from pathlib import Path
from typing import Any


class GPUUnavailableError(RuntimeError):
    """Raised when configuration requires CUDA but no usable GPU exists."""


def _torch_info() -> dict[str, Any]:
    info: dict[str, Any] = {"torch_installed": False}
    try:
        import torch
    except ImportError:
        return info
    info.update(
        {
            "torch_installed": True,
            "torch_version": torch.__version__,
            "cuda_available": bool(torch.cuda.is_available()),
            "cuda_runtime": torch.version.cuda,
            "gpu_count": int(torch.cuda.device_count()) if torch.cuda.is_available() else 0,
        }
    )
    if info["cuda_available"]:
        properties = torch.cuda.get_device_properties(0)
        info.update(
            {
                "gpu_name": torch.cuda.get_device_name(0),
                "gpu_capability": list(torch.cuda.get_device_capability(0)),
                "vram_total_bytes": int(properties.total_memory),
                "vram_free_bytes": int(torch.cuda.mem_get_info(0)[0]),
                "bf16_supported": bool(torch.cuda.is_bf16_supported()),
                "tf32_allowed": bool(torch.backends.cuda.matmul.allow_tf32),
            }
        )
    return info


def _optional_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for module_name in ("numpy", "pandas", "pymc", "arviz", "xgboost", "jax"):
        try:
            module = __import__(module_name)
            versions[module_name] = getattr(module, "__version__", "unknown")
        except ImportError:
            versions[module_name] = None
    return versions


def benchmark_devices(sizes: tuple[int, ...] = (512, 2048), repeats: int = 3) -> dict[str, Any]:
    """Time float32 matmul on CPU and (if present) CUDA. Returns seconds."""
    try:
        import torch
    except ImportError:
        return {"available": False}
    results: dict[str, Any] = {"available": True, "sizes": list(sizes)}
    for device in ["cpu"] + (["cuda"] if torch.cuda.is_available() else []):
        timings: list[float] = []
        for size in sizes:
            matrix = torch.randn(size, size, device=device)
            if device == "cuda":
                torch.cuda.synchronize()
            start = time.perf_counter()
            for _ in range(repeats):
                matrix @ matrix
            if device == "cuda":
                torch.cuda.synchronize()
            timings.append((time.perf_counter() - start) / repeats)
        results[device] = timings
    if "cuda" in results:
        results["cuda_speedup_largest"] = float(results["cpu"][-1] / max(results["cuda"][-1], 1e-9))
    return results


def collect_hardware_report(run_benchmark: bool = True) -> dict[str, Any]:
    report: dict[str, Any] = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python_version": sys.version,
        "torch": _torch_info(),
        "package_versions": _optional_versions(),
    }
    if run_benchmark:
        report["benchmark"] = benchmark_devices()
    return report


def write_hardware_artifacts(output_dir: str | Path, run_benchmark: bool = True) -> dict[str, Any]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    report = collect_hardware_report(run_benchmark=run_benchmark)
    (destination / "hardware_report.json").write_text(
        json.dumps({k: v for k, v in report.items() if k != "benchmark"}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    if run_benchmark:
        (destination / "gpu_benchmark.json").write_text(
            json.dumps(report.get("benchmark", {}), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    lines = [f"platform: {report['platform']}", f"python: {sys.version.split()[0]}"]
    torch_info = report["torch"]
    if torch_info.get("cuda_available"):
        lines += [
            f"gpu: {torch_info['gpu_name']} ({torch_info['vram_total_bytes'] / 2**30:.1f} GiB)",
            f"cuda_runtime: {torch_info['cuda_runtime']}",
            f"bf16: {torch_info['bf16_supported']}",
        ]
    else:
        lines.append("gpu: none")
    for name, version in report["package_versions"].items():
        lines.append(f"{name}: {version}")
    (destination / "environment_gpu.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def select_device(requested: str = "auto", require: bool = False) -> str:
    """Resolve 'auto'/'cuda'/'cpu' against actual availability.

    With ``require=True`` a missing GPU raises instead of silently using CPU.
    """
    try:
        import torch

        cuda_ok = torch.cuda.is_available()
    except ImportError:
        cuda_ok = False
    if requested == "cpu":
        return "cpu"
    if requested in ("cuda", "auto"):
        if cuda_ok:
            return "cuda"
        if require or requested == "cuda":
            raise GPUUnavailableError(
                "Configuration requires CUDA but torch.cuda.is_available() is False. "
                "Install a CUDA-enabled PyTorch build (see https://pytorch.org) or set "
                "runtime.device: cpu / require_gpu: false explicitly."
            )
        return "cpu"
    raise ValueError(f"Unknown device request: {requested!r}")


def require_gpu() -> None:
    select_device("cuda", require=True)
