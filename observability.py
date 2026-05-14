"""
╔══════════════════════════════════════════════════════════════════════════╗
║  CUSTOMIZATION POINT  ·  observability.py                                ║
║                                                                          ║
║  Single sink for all session events. Default writes JSONL + colored      ║
║  console lines. Replace _emit() to ship to Datadog / OTLP / your         ║
║  warehouse without touching the rest of the codebase.                    ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

import config


# ────────────────────────────────────────────────────────────────────────── #
#  Sink — replace this function to ship events anywhere.                    #
# ────────────────────────────────────────────────────────────────────────── #
def _emit(event: dict[str, Any]) -> None:
    if config.LOG_TOOL_CALLS:
        sys.stderr.write(f"  · {event['kind']:<14} "
                         f"{_short(event.get('data', {}))}\n")
    if config.TRANSCRIPT_PATH:
        with open(config.TRANSCRIPT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")


# ────────────────────────────────────────────────────────────────────────── #
#  Public API used elsewhere                                                #
# ────────────────────────────────────────────────────────────────────────── #
def log_event(kind: str, **data: Any) -> None:
    _emit({"ts": time.time(), "kind": kind, "data": data})


def log_tool_call(name: str, args: dict[str, Any]) -> None:
    log_event("tool_call", tool=name, args=args)


def log_tool_result(name: str, raw_result: str) -> None:
    try:
        parsed = json.loads(raw_result)
    except json.JSONDecodeError:
        parsed = {"raw": raw_result}
    log_event("tool_result", tool=name, result=parsed)


def _short(obj: Any, n: int = 140) -> str:
    s = json.dumps(obj, default=str)
    return s if len(s) <= n else s[: n - 1] + "…"
