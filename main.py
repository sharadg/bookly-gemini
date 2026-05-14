"""
Bookly Gemini Live agent — CLI entry point.

Usage:
    export GOOGLE_API_KEY=...
    python main.py            # text mode (default)
    python main.py --voice    # full Gemini Live bidi audio
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from orchestration import BooklyLiveAgent
from prompts import OPENING_GREETING


def parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bookly Gemini Live agent")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--text", action="store_true", help="text chat (default)")
    mode.add_argument("--voice", action="store_true", help="voice chat (bidi audio)")
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
