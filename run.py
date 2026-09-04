"""Start the QP-TRACKING server.

    python run.py            # serve on the configured host/port
    python run.py --reload   # auto-restart when backend code changes
"""

from __future__ import annotations

import argparse
import webbrowser

import uvicorn

from backend.config import settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the QP-TRACKING server")
    parser.add_argument("--host", default=settings.server.host)
    parser.add_argument("--port", type=int, default=settings.server.port)
    parser.add_argument("--reload", action="store_true", help="restart on code changes")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    args = parser.parse_args()

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
