"""Logging setup. Uses `rich` when installed, plain stderr otherwise."""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

_CONFIGURED = False

#: Patterns scrubbed from every log record so credentials cannot reach a file.
_SECRET_PATTERNS = [
    re.compile(r"(?i)(://[^:/\s]+:)([^@/\s]+)(@)"),          # user:pass@host
    re.compile(r"(?i)((?:password|passwd|pwd|token|api[_-]?key|secret)\s*[=:]\s*)(\S+)"),
]


class _RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            return True
        redacted = message
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub(r"\1***\3" if pattern.groups == 3 else r"\1***", redacted)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def setup_logging(
    level: str = "INFO",
    log_file: str | Path | None = None,
    use_rich: bool = True,
) -> logging.Logger:
    """Configure the root `dynamicgraph` logger. Idempotent."""
    global _CONFIGURED

    logger = logging.getLogger("dynamicgraph")
    numeric = getattr(logging, str(level).upper(), logging.INFO)
    logger.setLevel(numeric)

    if _CONFIGURED:
        for handler in logger.handlers:
            handler.setLevel(numeric)
        return logger

    logger.handlers.clear()
    logger.propagate = False
    redactor = _RedactingFilter()

    handler: logging.Handler
    if use_rich:
        try:
            from rich.logging import RichHandler

            handler = RichHandler(rich_tracebacks=True, show_path=False, markup=False)
            handler.setFormatter(logging.Formatter("%(message)s", datefmt="%H:%M:%S"))
        except Exception:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(
                logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
            )
    else:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
        )
    handler.setLevel(numeric)
    handler.addFilter(redactor)
    logger.addHandler(handler)

    if log_file:
        path = Path(log_file)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(path, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(
                logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
            )
            file_handler.addFilter(redactor)
            logger.addHandler(file_handler)
        except OSError as exc:  # pragma: no cover - environment dependent
            logger.warning("Could not open log file %s: %s", path, exc)

    _CONFIGURED = True
    return logger


def get_logger(name: str) -> logging.Logger:
    """Child logger under the `dynamicgraph` namespace."""
    if not name.startswith("dynamicgraph"):
        name = f"dynamicgraph.{name}"
    return logging.getLogger(name)
