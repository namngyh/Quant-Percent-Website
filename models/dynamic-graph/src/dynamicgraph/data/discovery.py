"""Discovery of candidate local data sources.

Scans the project tree and a small set of well-known locations for anything
that could hold VN30 price history: SQLite / DuckDB files, Parquet, CSV,
Feather, HDF5, plus connection strings declared in `.env` / YAML / TOML / JSON
configuration files.

Two hard rules:
  * every file is opened READ-ONLY;
  * no credential is ever returned, logged or written to an artifact -- only
    the *presence* of a connection string is reported.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable

from dynamicgraph.logging_config import get_logger

logger = get_logger(__name__)

FILE_PATTERNS: dict[str, tuple[str, ...]] = {
    "sqlite": (".db", ".sqlite", ".sqlite3", ".dat", ".db3"),
    "duckdb": (".duckdb", ".ddb"),
    "parquet": (".parquet", ".pq"),
    "csv": (".csv", ".csv.gz", ".txt"),
    "feather": (".feather", ".arrow"),
    "hdf5": (".h5", ".hdf5"),
}

CONFIG_PATTERNS = (".env", ".yaml", ".yml", ".toml", ".json", ".ini", ".cfg")

#: Directories that are never worth walking.
SKIP_DIR_NAMES = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "site-packages", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "$Recycle.Bin", "System Volume Information", "Windows", "AppData",
    ".cache", "dist", "build", ".idea", ".vscode",
}

#: Regexes that indicate a connection string. Only the *scheme* is reported.
_CONN_RE = re.compile(
    r"(?i)\b(sqlite|duckdb|postgres(?:ql)?(?:\+\w+)?|mysql(?:\+\w+)?|mssql(?:\+\w+)?|"
    r"clickhouse|mongodb)://"
)
_SECRET_KEY_RE = re.compile(r"(?i)(password|passwd|pwd|secret|token|api[_-]?key)")

MAX_FILE_SCAN = 60_000


@dataclass
class DataSourceCandidate:
    """A single discovered data source and everything we learned about it."""

    path: str
    kind: str
    size_bytes: int = 0
    modified: str | None = None
    readable: bool = False
    tables: list[str] = field(default_factory=list)
    n_tables: int = 0
    n_rows_estimate: int = 0
    n_tickers: int | None = None
    date_min: str | None = None
    date_max: str | None = None
    has_adjusted_price: bool = False
    has_volume: bool = False
    has_turnover: bool = False
    has_sector: bool = False
    missing_ratio: float | None = None
    contains_index_symbol: bool = False
    matched_universe_tickers: int = 0
    backend: str = "unknown"
    notes: list[str] = field(default_factory=list)
    score: float = 0.0
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Filesystem walking
# ---------------------------------------------------------------------------
def _iter_files(roots: Iterable[Path], max_depth: int = 6) -> Iterable[Path]:
    seen = 0
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        root_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root, topdown=True):
            current = Path(dirpath)
            if len(current.parts) - root_depth >= max_depth:
                dirnames[:] = []
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES and not d.startswith(".git")]
            for name in filenames:
                seen += 1
                if seen > MAX_FILE_SCAN:
                    logger.warning("Discovery file budget (%d) exhausted; stopping walk.", MAX_FILE_SCAN)
                    return
                yield current / name


def _classify(path: Path) -> str | None:
    lowered = path.name.lower()
    for kind, suffixes in FILE_PATTERNS.items():
        for suffix in suffixes:
            if lowered.endswith(suffix):
                return kind
    return None


def _is_sqlite(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def _is_duckdb(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            head = handle.read(16)
        return b"DUCK" in head
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Per-kind inspection (all read-only)
# ---------------------------------------------------------------------------
def _inspect_sqlite(candidate: DataSourceCandidate) -> None:
    from dynamicgraph.data.schema_inference import inspect_sqlite_schema

    try:
        info = inspect_sqlite_schema(Path(candidate.path))
    except Exception as exc:
        candidate.notes.append(f"unreadable sqlite: {exc}")
        return
    candidate.readable = True
    candidate.backend = info.get("backend", "generic_sqlite")
    candidate.tables = list(info.get("tables", {}).keys())
    candidate.n_tables = len(candidate.tables)
    candidate.n_rows_estimate = int(info.get("total_rows", 0))
    candidate.n_tickers = info.get("n_tickers")
    candidate.date_min = info.get("date_min")
    candidate.date_max = info.get("date_max")
    candidate.has_adjusted_price = bool(info.get("has_adjusted_price"))
    candidate.has_volume = bool(info.get("has_volume"))
    candidate.has_turnover = bool(info.get("has_turnover"))
    candidate.has_sector = bool(info.get("has_sector"))
    candidate.contains_index_symbol = bool(info.get("contains_index_symbol"))
    candidate.matched_universe_tickers = int(info.get("matched_universe_tickers", 0))
    candidate.detail = info
    candidate.notes.extend(info.get("notes", []))


def _inspect_duckdb(candidate: DataSourceCandidate) -> None:
    try:
        import duckdb
    except ImportError:
        candidate.notes.append("duckdb not installed; install extras `db` to inspect")
        return
    try:
        con = duckdb.connect(candidate.path, read_only=True)
    except Exception as exc:
        candidate.notes.append(f"unreadable duckdb: {exc}")
        return
    try:
        candidate.readable = True
        candidate.backend = "duckdb"
        rows = con.execute("SELECT table_name FROM information_schema.tables").fetchall()
        candidate.tables = [r[0] for r in rows]
        candidate.n_tables = len(candidate.tables)
        total = 0
        for table in candidate.tables[:50]:
            try:
                total += con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            except Exception:
                continue
        candidate.n_rows_estimate = total
    finally:
        con.close()


def _inspect_tabular(candidate: DataSourceCandidate, universe_hint: set[str]) -> None:
    """Peek at a CSV/Parquet/Feather file without loading it fully."""
    from dynamicgraph.data.schema_inference import infer_columns_from_names

    path = Path(candidate.path)
    try:
        import pandas as pd

        if candidate.kind == "parquet":
            frame = pd.read_parquet(path)
            sample = frame.head(5000)
            n_rows = len(frame)
        elif candidate.kind == "feather":
            frame = pd.read_feather(path)
            sample = frame.head(5000)
            n_rows = len(frame)
        elif candidate.kind == "hdf5":
            candidate.notes.append("hdf5 inspection requires an explicit key; skipped")
            return
        else:
            sample = pd.read_csv(path, nrows=5000)
            n_rows = sum(1 for _ in path.open("r", encoding="utf-8", errors="ignore")) - 1
    except Exception as exc:
        candidate.notes.append(f"unreadable {candidate.kind}: {exc}")
        return

    candidate.readable = True
    candidate.backend = candidate.kind
    candidate.n_rows_estimate = max(n_rows, 0)
    mapping = infer_columns_from_names(list(sample.columns))
    candidate.detail = {"columns": list(map(str, sample.columns)), "column_map": mapping}
    candidate.has_adjusted_price = "adjusted_close" in mapping
    candidate.has_volume = "volume" in mapping
    candidate.has_turnover = "turnover" in mapping
    candidate.has_sector = "sector" in mapping

    if "ticker" in mapping:
        tickers = set(sample[mapping["ticker"]].astype(str).str.upper().unique())
        candidate.n_tickers = len(tickers)
        candidate.matched_universe_tickers = len(tickers & universe_hint)
        candidate.contains_index_symbol = any("VN30" in t or "VNINDEX" in t for t in tickers)
    if "date" in mapping:
        try:
            dates = pd.to_datetime(sample[mapping["date"]], errors="coerce").dropna()
            if len(dates):
                candidate.date_min = str(dates.min().date())
                candidate.date_max = str(dates.max().date())
        except Exception:
            pass
    close_col = mapping.get("close")
    if close_col and close_col in sample.columns:
        candidate.missing_ratio = float(sample[close_col].isna().mean())


def _scan_config_file(path: Path) -> list[dict[str, Any]]:
    """Report connection strings *without* their credentials."""
    findings: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return findings
    if len(text) > 2_000_000:
        return findings
    for match in _CONN_RE.finditer(text):
        findings.append(
            {
                "file": str(path),
                "scheme": match.group(1).lower(),
                "credentials_present": bool(_SECRET_KEY_RE.search(text)),
                "value": "<redacted - connection string found, contents never stored>",
            }
        )
    return findings


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------
def rank_candidates(candidates: list[DataSourceCandidate]) -> list[DataSourceCandidate]:
    """Score candidates by the priority order given in the project brief.

    Priority: most tickers > longest history > fewest missing > adjusted price
    > volume/turnover > freshest data.
    """
    import datetime as _dt

    for cand in candidates:
        score = 0.0
        if not cand.readable:
            cand.score = -1.0
            continue

        # 1. ticker coverage (dominant term)
        n_tickers = cand.n_tickers or 0
        score += 1000.0 * min(n_tickers, 3000) / 3000.0
        score += 400.0 * min(cand.matched_universe_tickers, 30) / 30.0
        if cand.contains_index_symbol:
            score += 200.0

        # 2. history length
        if cand.date_min and cand.date_max:
            try:
                span_days = (
                    _dt.date.fromisoformat(cand.date_max) - _dt.date.fromisoformat(cand.date_min)
                ).days
                score += 300.0 * min(span_days, 20 * 365) / (20 * 365)
            except ValueError:
                pass

        # 3. missing values
        if cand.missing_ratio is not None:
            score += 100.0 * max(0.0, 1.0 - min(cand.missing_ratio, 1.0))

        # 4-5. field richness
        score += 120.0 if cand.has_adjusted_price else 0.0
        score += 60.0 if cand.has_volume else 0.0
        score += 40.0 if cand.has_turnover else 0.0
        score += 30.0 if cand.has_sector else 0.0

        # 6. freshness
        if cand.date_max:
            try:
                age = (_dt.date.today() - _dt.date.fromisoformat(cand.date_max)).days
                score += 100.0 * max(0.0, 1.0 - min(age, 365) / 365.0)
            except ValueError:
                pass

        score += min(cand.n_rows_estimate, 10_000_000) / 10_000_000.0 * 50.0
        cand.score = round(score, 3)

    return sorted(candidates, key=lambda c: c.score, reverse=True)


def default_search_roots(project_root: Path) -> list[Path]:
    """Project tree first, then a conservative set of common data locations."""
    roots = [project_root]
    parent = project_root.parent
    if parent != project_root:
        roots.append(parent)

    home = Path.home()
    for extra in ("Desktop", "Documents", "Downloads", "data", ".dynamicgraph"):
        candidate = home / extra
        if candidate.exists():
            roots.append(candidate)

    if os.name == "nt":
        for drive in ("C:/", "D:/", "E:/"):
            drive_path = Path(drive)
            if not drive_path.exists():
                continue
            for name in ("Data", "data", "DataPro", "market_data", "quant"):
                candidate = drive_path / name
                if candidate.exists():
                    roots.append(candidate)
    else:
        for candidate in (Path("/data"), Path("/var/data")):
            if candidate.exists():
                roots.append(candidate)

    unique: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        resolved = root.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def discover_data_sources(
    roots: Iterable[Path] | None = None,
    project_root: Path | None = None,
    universe_hint: Iterable[str] | None = None,
    max_depth: int = 6,
    min_size_bytes: int = 4096,
) -> dict[str, Any]:
    """Walk the filesystem and return an inventory of candidate data sources."""
    from dynamicgraph.config import REPO_ROOT

    project_root = Path(project_root or REPO_ROOT)
    search_roots = list(roots) if roots is not None else default_search_roots(project_root)
    hint = {t.upper() for t in (universe_hint or [])}

    logger.info("Scanning %d root(s) for data sources", len(search_roots))

    candidates: list[DataSourceCandidate] = []
    connection_strings: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    for path in _iter_files(search_roots, max_depth=max_depth):
        name_lower = path.name.lower()
        if name_lower.endswith(CONFIG_PATTERNS) or name_lower == ".env":
            connection_strings.extend(_scan_config_file(path))

        kind = _classify(path)
        if kind is None:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_size < min_size_bytes:
            continue
        key = str(path.resolve()).lower()
        if key in seen_paths:
            continue
        seen_paths.add(key)

        # Content sniffing beats the extension: `.dat` files are frequently SQLite.
        if kind in {"sqlite", "csv"} and _is_sqlite(path):
            kind = "sqlite"
        elif kind == "sqlite" and not _is_sqlite(path):
            if _is_duckdb(path):
                kind = "duckdb"
            elif path.suffix.lower() == ".dat":
                continue  # opaque binary, not a database we can read
        if kind == "csv" and path.suffix.lower() == ".txt" and stat.st_size < 100_000:
            continue

        import datetime as _dt

        candidate = DataSourceCandidate(
            path=str(path),
            kind=kind,
            size_bytes=stat.st_size,
            modified=_dt.datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        )

        try:
            if kind == "sqlite":
                _inspect_sqlite(candidate)
            elif kind == "duckdb":
                _inspect_duckdb(candidate)
            else:
                _inspect_tabular(candidate, hint)
        except Exception as exc:  # pragma: no cover - defensive
            candidate.notes.append(f"inspection failed: {exc}")

        candidates.append(candidate)

    ranked = rank_candidates(candidates)
    relevant = [c for c in ranked if c.score > 0]

    logger.info(
        "Discovery finished: %d candidate file(s), %d readable, %d connection string(s)",
        len(candidates),
        len(relevant),
        len(connection_strings),
    )

    return {
        "search_roots": [str(r) for r in search_roots],
        "n_candidates": len(candidates),
        "candidates": [c.to_dict() for c in ranked],
        "recommended": relevant[0].to_dict() if relevant else None,
        "connection_strings": connection_strings,
    }


def write_inventory(inventory: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    """Persist the inventory as JSON + Markdown."""
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "data_inventory.json"
    md_path = out_dir / "data_inventory.md"

    json_path.write_text(json.dumps(inventory, indent=2, default=str), encoding="utf-8")

    lines: list[str] = [
        "# DynamicGraph - Local Data Inventory",
        "",
        "Generated by `python -m dynamicgraph.cli discover-data`.",
        "All sources were opened **read-only**. No credential values are stored here.",
        "",
        "## Search roots",
        "",
    ]
    lines += [f"- `{root}`" for root in inventory.get("search_roots", [])]
    lines += ["", "## Candidate data sources (ranked)", ""]
    lines += [
        "| # | Path | Kind | Size (MB) | Tables | Rows | Tickers | VN30 hits | Date range | Adj | Vol | Turnover | Sector | Score |",
        "|---|------|------|-----------|--------|------|---------|-----------|------------|-----|-----|----------|--------|-------|",
    ]
    for i, cand in enumerate(inventory.get("candidates", [])[:40], start=1):
        date_range = (
            f"{cand.get('date_min') or '?'} .. {cand.get('date_max') or '?'}"
            if cand.get("date_min") or cand.get("date_max")
            else "-"
        )
        lines.append(
            "| {i} | `{path}` | {kind} | {size:.1f} | {tables} | {rows} | {tick} | {hits} | {dr} | {adj} | {vol} | {to} | {sec} | {score} |".format(
                i=i,
                path=cand.get("path", ""),
                kind=cand.get("kind", ""),
                size=cand.get("size_bytes", 0) / 1e6,
                tables=cand.get("n_tables", 0),
                rows=cand.get("n_rows_estimate", 0),
                tick=cand.get("n_tickers") if cand.get("n_tickers") is not None else "-",
                hits=cand.get("matched_universe_tickers", 0),
                dr=date_range,
                adj="yes" if cand.get("has_adjusted_price") else "no",
                vol="yes" if cand.get("has_volume") else "no",
                to="yes" if cand.get("has_turnover") else "no",
                sec="yes" if cand.get("has_sector") else "no",
                score=cand.get("score", 0.0),
            )
        )

    recommended = inventory.get("recommended")
    lines += ["", "## Recommended source", ""]
    if recommended:
        lines += [
            f"- **Path**: `{recommended['path']}`",
            f"- **Backend**: `{recommended.get('backend')}`",
            f"- **Tables**: {', '.join(recommended.get('tables', [])) or '-'}",
            f"- **Tickers**: {recommended.get('n_tickers')}",
            f"- **Date range**: {recommended.get('date_min')} .. {recommended.get('date_max')}",
            f"- **Adjusted price available**: {recommended.get('has_adjusted_price')}",
            "",
            "Set this path in `config/local.yaml` under `data.database_path`.",
        ]
    else:
        lines += [
            "No usable data source was found.",
            "",
            "Create `config/local.yaml` from `config/local.example.yaml` and set",
            "`data.database_path` to your database, or export `DYNAMICGRAPH_DATABASE_URL`.",
        ]

    conns = inventory.get("connection_strings", [])
    lines += ["", "## Connection strings found in configuration files", ""]
    if conns:
        lines += ["| File | Scheme | Credentials present |", "|------|--------|---------------------|"]
        for conn in conns:
            lines.append(
                f"| `{conn['file']}` | {conn['scheme']} | {'yes' if conn['credentials_present'] else 'no'} |"
            )
        lines += ["", "> Values are never read into artifacts. Only the scheme is reported."]
    else:
        lines.append("None.")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def probe_sqlite_readonly(path: Path) -> bool:
    """Return True when the file can be opened read-only as SQLite."""
    try:
        uri = f"file:{Path(path).as_posix()}?mode=ro"
        con = sqlite3.connect(uri, uri=True, timeout=5)
        con.execute("SELECT 1 FROM sqlite_master LIMIT 1")
        con.close()
        return True
    except Exception:
        return False
