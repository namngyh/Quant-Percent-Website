"""Start the QP-TRACKING server.

    python run.py            # serve on the configured host/port
    python run.py --reload   # auto-restart when backend code changes
"""

from __future__ import annotations

import argparse
import socket
import webbrowser

import uvicorn

from backend.config import settings


def check_preconditions(host: str, port: int) -> str | None:
    """Return a human-readable reason we cannot start, or None if we can.

    Both failures checked here usually mean the same thing — the platform is
    already open in another window — and both would otherwise surface as a raw
    traceback, which says nothing about what to do about it.
    """
    import duckdb

    from backend.data.store import db_path

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return (
                f"Cong {port} dang duoc dung."
                "\n      QP-TRACKING co the dang mo o mot cua so khac."
                f"\n      Thu mo http://{host}:{port} truoc,"
                "\n      hoac dong cua so do roi chay lai."
            )

    try:
        duckdb.connect(str(db_path())).close()
    except duckdb.IOException:
        return (
            "Khong mo duoc database - mot tien trinh khac dang giu no."
            "\n      DuckDB chi cho phep mot tien trinh ghi cung luc."
            "\n      Dong cua so QP-TRACKING dang chay (hoac scripts/backfill.py)"
            "\n      roi thu lai."
        )

    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the QP-TRACKING server")
    parser.add_argument("--host", default=settings.server.host)
    parser.add_argument("--port", type=int, default=settings.server.port)
    parser.add_argument("--reload", action="store_true", help="restart on code changes")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    args = parser.parse_args()

    problem = check_preconditions(args.host, args.port)
    if problem:
        print(f"\n  [!] {problem}\n")
        raise SystemExit(1)

    url = f"http://{args.host}:{args.port}"
    print(f"\n  QP-TRACKING  ->  {url}\n")

    if not args.no_browser and not args.reload:
        webbrowser.open(url)

    uvicorn.run(
        "backend.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
