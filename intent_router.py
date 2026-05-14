"""
╔══════════════════════════════════════════════════════════════════════════╗
║  CUSTOMIZATION POINT  ·  intent_router.py                                ║
║                                                                          ║
║  Optional pre-LLM intent classifier. Off by default — Gemini's tool      ║
║  descriptions already route well. Turn this on when you want:            ║
║                                                                          ║
║    - hard routing to a different model for some intents (e.g. cheap      ║
║      model for FAQ, premium for refunds)                                 ║
║    - deterministic deflection rules ("anything containing 'cancel' goes  ║
║      straight to a human")                                               ║
║    - metrics on intent distribution                                      ║
║                                                                          ║
║  Replace the stub below with a real classifier — keyword, regex, or a    ║
║  small fast LLM call. Return one of the Intent enum values.              ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

from enum import Enum


class Intent(str, Enum):
    ORDER_STATUS = "order_status"
    RETURN = "return"
    FAQ = "faq"
    ESCALATION = "escalation"
    UNKNOWN = "unknown"


# *** CUSTOMIZATION: flip to True to route through this layer ***
ENABLED = False


_KEYWORDS = {
    Intent.RETURN:      ["return", "refund", "send back", "rma"],
    Intent.ORDER_STATUS:["order", "track", "where is", "ship", "delivery"],
    Intent.FAQ:         ["password", "shipping", "policy", "cancel", "gift"],
    Intent.ESCALATION:  ["human", "agent", "manager", "speak to", "complaint"],
}


def classify(text: str) -> Intent:
    """Cheap keyword classifier. Replace with your model of choice."""
    t = text.lower()
    for intent, kws in _KEYWORDS.items():
        if any(k in t for k in kws):
            return intent
    return Intent.UNKNOWN
