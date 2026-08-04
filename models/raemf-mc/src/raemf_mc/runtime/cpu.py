"""Stable CPU thread policy and lightweight stage profiling."""

from __future__ import annotations

import os
import platform
import time
import tracemalloc
from dataclasses import dataclass
from typing import Any


def configure_cpu_runtime(config: dict[str, Any]) -> dict[str, Any]:
    """Apply one bounded thread count without touching CUDA APIs."""
    runtime = dict(config.get("runtime", config))
    device = str(runtime.get("device", "cpu"))
    if device != "cpu":
        raise ValueError("CPU downside profiles require runtime.device: cpu")
    threads = int(runtime.get("max_threads", 4))
    if threads <= 0:
        raise ValueError("runtime.max_threads must be positive")
    for variable in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ[variable] = str(threads)
    torch_threads: int | None = None
    try:
        import torch

        torch.set_num_threads(threads)
        try:
            torch.set_num_interop_threads(max(1, min(2, threads)))
        except RuntimeError:
            pass
        torch_threads = int(torch.get_num_threads())
    except ImportError:
        pass
    return {
        "device": "cpu",
        "max_threads": threads,
        "torch_threads": torch_threads,
        "platform": platform.platform(),
        "cuda_used": False,
    }


def current_rss_bytes() -> int | None:
    """Return RSS, or Windows peak working set when psutil is unavailable."""
    try:
        import psutil

        return int(psutil.Process().memory_info().rss)
    except ImportError:
        if os.name != "nt":
            return None
        try:
            import ctypes
            from ctypes import wintypes

            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            process = ctypes.windll.kernel32.GetCurrentProcess()
            memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
            memory_info.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(ProcessMemoryCounters),
                wintypes.DWORD,
            ]
            memory_info.restype = wintypes.BOOL
            success = memory_info(
                process,
                ctypes.byref(counters),
                counters.cb,
            )
            return int(counters.PeakWorkingSetSize) if success else None
        except (AttributeError, OSError):
            return None


@dataclass
class StageRecord:
    stage: str
    horizon: int | None
    fold: int | None
    wall_time: float
    cpu_time: float
    peak_rss: int | str
    peak_python_bytes: int
    cache_status: str
    thread_count: int

    def to_dict(self) -> dict[str, Any]:
        return vars(self).copy()


class StageProfiler:
    """Context manager collecting required runtime benchmark columns."""

    def __init__(
        self,
        records: list[dict[str, Any]],
        stage: str,
        *,
        horizon: int | None = None,
        fold: int | None = None,
        cache_status: str = "not_applicable",
        thread_count: int = 1,
    ) -> None:
        self.records = records
        self.stage = stage
        self.horizon = horizon
        self.fold = fold
        self.cache_status = cache_status
        self.thread_count = thread_count

    def __enter__(self) -> "StageProfiler":
        self.wall_start = time.perf_counter()
        self.cpu_start = time.process_time()
        self.start_rss = current_rss_bytes()
        tracemalloc.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        _, peak_python = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        end_rss = current_rss_bytes()
        rss_values = [value for value in (self.start_rss, end_rss) if value is not None]
        record = StageRecord(
            stage=self.stage,
            horizon=self.horizon,
            fold=self.fold,
            wall_time=time.perf_counter() - self.wall_start,
            cpu_time=time.process_time() - self.cpu_start,
            peak_rss=max(rss_values) if rss_values else "not_available",
            peak_python_bytes=int(peak_python),
            cache_status=self.cache_status,
            thread_count=self.thread_count,
        )
        self.records.append(record.to_dict())
