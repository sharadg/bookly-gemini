"""
╔══════════════════════════════════════════════════════════════════════════╗
║  CUSTOMIZATION POINT  ·  config.py                                       ║
║                                                                          ║
║  Single file for every knob in the agent. Change values here; nothing    ║
║  else in the codebase should hard-code these.                            ║
╚══════════════════════════════════════════════════════════════════════════╝

Sections below are intentionally short and labeled. If you find yourself
threading a constant through several files, add it here instead.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


# ────────────────────────────────────────────────────────────────────────── #
#  MODEL                                                                    #
# ────────────────────────────────────────────────────────────────────────── #
# Gemini Live model. Two production options at time of writing:
#   - "gemini-2.0-flash-live-001"   (general availability, low latency)
#   - "gemini-2.5-flash-preview-native-audio-dialog" (more natural prosody,
#     preview)
# Override via env BOOKLY_MODEL.
MODEL = os.environ.get("BOOKLY_MODEL", "gemini-3.1-flash-live-preview")

# API key. Required.
API_KEY = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")

# Pin the API version that exposes Live. v1beta is correct as of this writing.
API_VERSION = "v1beta"


# ────────────────────────────────────────────────────────────────────────── #
#  VOICE                                                                    #
# ────────────────────────────────────────────────────────────────────────── #
# Prebuilt voice options (Live API): Puck, Charon, Kore, Fenrir, Aoede,
# Leda, Orus, Zephyr. Pick by listening — they differ in warmth and pace.
VOICE = os.environ.get("BOOKLY_VOICE", "Kore")

# Gemini Live audio I/O contract — do not change unless the API changes.
INPUT_SAMPLE_RATE = 16_000   # PCM 16-bit mono, what the model expects
OUTPUT_SAMPLE_RATE = 24_000  # PCM 16-bit mono, what the model emits
AUDIO_CHANNELS = 1
AUDIO_DTYPE = "int16"
INPUT_MIME = f"audio/pcm;rate={INPUT_SAMPLE_RATE}"


# ────────────────────────────────────────────────────────────────────────── #
#  ORCHESTRATION                                                            #
# ────────────────────────────────────────────────────────────────────────── #
# Hard cap on server tool-call *batches* per assistant turn (each batch is
# one `response.tool_call` from `live.receive()`, not each streaming chunk).
# Catches infinite tool loops without breaking AUDIO streaming.
MAX_TOOL_ITERS_PER_TURN = 5

# Number of consecutive failed turns before forcing escalation.
ESCALATION_AFTER_FAILED_TURNS = 2

# Maximum context window the agent will retain in working memory
# (number of user-turn / assistant-turn pairs before older context is
# summarized). Live API handles this internally; this is for our
# session-level memory.
MAX_TURNS_IN_MEMORY = 20


# ────────────────────────────────────────────────────────────────────────── #
#  POLICY                                                                   #
# ────────────────────────────────────────────────────────────────────────── #
# These are the policy constants the *tools* enforce. The system prompt
# does NOT see them — the model only sees what tools return.

RETURN_WINDOW_DAYS = 30
NON_RETURNABLE_CATEGORIES = ("digital", "gift_card")
CONDITION_REQUIRED = "unused, original packaging"
REFUND_BUSINESS_DAYS = 5


# ────────────────────────────────────────────────────────────────────────── #
#  OBSERVABILITY                                                            #
# ────────────────────────────────────────────────────────────────────────── #
# Toggle verbose tool-call logging (prints to stderr).
LOG_TOOL_CALLS = True

# Where to write the session transcript JSONL (None disables).
TRANSCRIPT_PATH = os.environ.get("BOOKLY_TRANSCRIPT", "session.jsonl")
