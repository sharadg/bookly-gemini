"""
╔══════════════════════════════════════════════════════════════════════════╗
║  CUSTOMIZATION POINT  ·  guardrails.py                                   ║
║                                                                          ║
║  Four hooks the orchestrator calls at fixed points in each turn:         ║
║                                                                          ║
║      pre_user_text     →  inbound user text / transcript                 ║
║      pre_tool_call     →  before dispatching a tool                      ║
║      post_tool_call    →  after a tool returns                           ║
║      pre_agent_response→  before audio playback / text output            ║
║                                                                          ║
║  Each hook can:                                                          ║
║      - return the (possibly modified) input to continue,                 ║
║      - return None / raise GuardrailBlock to abort and override the      ║
║        agent's response.                                                 ║
║                                                                          ║
║  Defaults are conservative; replace with your own checks. This file is   ║
║  where compliance, PII scrubbing, jailbreak detection, and content       ║
║  filters live in a production setup.                                     ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import config
from tools._registry import Session


# ────────────────────────────────────────────────────────────────────────── #
#  Control-flow primitive                                                   #
# ────────────────────────────────────────────────────────────────────────── #
class GuardrailBlock(Exception):
    """Raise from any hook to abort the current turn and play a canned
    response to the user. Carries the message the agent should speak."""

    def __init__(self, speak: str, *, log_reason: str = "blocked"):
        self.speak = speak
        self.log_reason = log_reason
        super().__init__(log_reason)


@dataclass
class GuardrailDecision:
    """Returned by hooks that may transform input. `allow=False` aborts."""
    allow: bool = True
    payload: Any = None
    speak_instead: str | None = None
    reason: str = ""


# ────────────────────────────────────────────────────────────────────────── #
#  Hook 1 — pre_user_text                                                   #
#  Fires on every inbound user message (text or transcribed audio).         #
#  Use for: jailbreak detection, prompt-injection filters, PII redaction,   #
#  abuse / profanity policies, language detection, locale routing.          #
# ────────────────────────────────────────────────────────────────────────── #
PROMPT_INJECTION_PATTERNS = [
    r"ignore (all )?previous instructions",
    r"system prompt",
    r"you are now",
    r"act as ",
]


def pre_user_text(session: Session, text: str) -> GuardrailDecision:
    text_l = text.lower()

    # *** CUSTOMIZATION: add your own patterns or call an external safety classifier ***
    for pat in PROMPT_INJECTION_PATTERNS:
        if re.search(pat, text_l):
            return GuardrailDecision(
                allow=False,
                reason="prompt_injection",
                speak_instead=(
                    "I can only help with Bookly orders, returns, and "
                    "general questions. What can I do for you?"
                ),
            )

    return GuardrailDecision(allow=True, payload=text)


# ────────────────────────────────────────────────────────────────────────── #
#  Hook 2 — pre_tool_call                                                   #
#  Fires before a tool is dispatched. Use for: per-tool rate limits,        #
#  per-tool authorization, argument validation beyond the JSON schema,      #
#  blocking destructive tools in read-only mode, etc.                       #
# ────────────────────────────────────────────────────────────────────────── #
# *** CUSTOMIZATION: set to True to refuse all tools that mutate state ***
READ_ONLY_MODE = False

MUTATING_TOOLS = {"submit_return", "escalate_to_human"}


def pre_tool_call(
    session: Session,
    tool_name: str,
    args: dict[str, Any],
) -> GuardrailDecision:
    if READ_ONLY_MODE and tool_name in MUTATING_TOOLS:
        return GuardrailDecision(
            allow=False,
            reason="read_only_mode",
            speak_instead=(
                "I can look that up but I can't make changes right now. "
                "Let me hand you to a teammate who can."
            ),
        )

    # *** CUSTOMIZATION: per-tool rate-limit example ***
    # if tool_name == "submit_return" and session.failed_turns > 1:
    #     return GuardrailDecision(allow=False, reason="rate_limited", ...)

    return GuardrailDecision(allow=True, payload=args)


# ────────────────────────────────────────────────────────────────────────── #
#  Hook 3 — post_tool_call                                                  #
#  Fires after a tool returns. Use for: PII scrubbing of tool output,       #
#  redaction of internal IDs the model shouldn't repeat verbatim, metric   #
#  emission, alerting on error codes.                                       #
# ────────────────────────────────────────────────────────────────────────── #
def post_tool_call(
    session: Session,
    tool_name: str,
    args: dict[str, Any],
    raw_result: str,
) -> GuardrailDecision:
    # *** CUSTOMIZATION: scrub internal fields before showing model ***
    # Example: blank out tracking-number prefixes that reveal carrier
    # routing internals. Default is pass-through.
    return GuardrailDecision(allow=True, payload=raw_result)


# ────────────────────────────────────────────────────────────────────────── #
#  Hook 4 — pre_agent_response                                              #
#  Fires after Gemini produces a response, before it reaches the speaker    #
#  or text channel. Use for: profanity filters, brand-voice enforcement,    #
#  hallucinated-claim detection (e.g. agent quoting a refund amount the    #
#  tools never returned).                                                   #
# ────────────────────────────────────────────────────────────────────────── #
FORBIDDEN_CLAIMS = [
    r"\bguaranteed?\b.*\brefund\b",
    r"\bfree shipping forever\b",
]


def pre_agent_response(session: Session, text: str) -> GuardrailDecision:
    text_l = (text or "").lower()
    for pat in FORBIDDEN_CLAIMS:
        if re.search(pat, text_l):
            return GuardrailDecision(
                allow=False,
                reason="forbidden_claim",
                speak_instead=(
                    "Let me check on that. One moment — I'll pull up "
                    "the policy."
                ),
            )
    return GuardrailDecision(allow=True, payload=text)


# ────────────────────────────────────────────────────────────────────────── #
#  Escalation policy — called by the orchestrator each turn                 #
# ────────────────────────────────────────────────────────────────────────── #
def should_force_escalation(session: Session) -> bool:
    """Return True if the orchestrator should bail out and escalate
    even if the model hasn't called escalate_to_human itself."""
    return session.failed_turns >= config.ESCALATION_AFTER_FAILED_TURNS
