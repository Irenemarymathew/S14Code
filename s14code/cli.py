"""S14Code CLI: ``s14code serve``."""

from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(prog="s14code")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="run the surface service")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=int(os.environ.get("S14_PORT", "8115")))
    args = parser.parse_args()

    if args.command == "serve":
        import uvicorn

        uvicorn.run("s14code.main:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
