"""
Bookly Gemini Live agent — CLI entry point.

Usage:
    export GOOGLE_API_KEY=...
    python main.py            # text mode (default)
    python main.py --voice    # full Gemini Live bidi audio (CLI)
    python main.py --web      # voice in the browser (local server)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from orchestration import BooklyLiveAgent
from prompts import OPENING_GREETING


def parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bookly Gemini Live agent")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--text", action="store_true", help="text chat (default)")
    mode.add_argument("--voice", action="store_true", help="voice chat (bidi audio)")
    p.add_argument(
        "--web",
        action="store_true",
        help="browser voice UI (local FastAPI server; set BOOKLY_WEB_HOST / BOOKLY_WEB_PORT)",
    )
    return p.parse_args()


async def amain(args: argparse.Namespace) -> int:
    agent = BooklyLiveAgent(modality="AUDIO" if args.voice else "TEXT")
    print(f"\nAgent: {OPENING_GREETING}")
    if args.voice:
        await agent.run_voice()
    else:
        await agent.run_text()
    return 0


def main() -> int:
    args = parse()
    if args.web:
        import uvicorn

        host = os.environ.get("BOOKLY_WEB_HOST", "127.0.0.1")
        port = int(os.environ.get("BOOKLY_WEB_PORT", "8765"))
        print(f"\nBookly web voice UI: http://{host}:{port}/\n")
        uvicorn.run("web_server:app", host=host, port=port, reload=False)
        return 0
    try:
        return asyncio.run(amain(args))
    except KeyboardInterrupt:
        print()
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"\nFatal: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
