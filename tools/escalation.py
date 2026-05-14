"""
Human handoff. In production this creates a ticket in your CCaaS system
and posts a structured summary so the human picks up mid-thread without
the customer repeating themselves.
"""

from __future__ import annotations

from ._registry import Session, tool, ok


@tool(
    name="escalate_to_human",
    description=(
        "Hand off to a human agent. Call this when: the customer is "
        "upset and asks for a person; the request is outside the "
        "supported scope (legal, accessibility, payment disputes, "
        "account suspension); or you've failed to make progress after "
        "two turns. Include a concise summary so the human doesn't ask "
        "the customer to repeat themselves."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "reason": {
                "type": "STRING",
                "enum": [
                    "customer_request",
                    "out_of_scope",
                    "agent_stuck",
                    "sensitive",
                ],
            },
            "summary": {
                "type": "STRING",
                "description": "1–3 sentence handoff summary.",
            },
        },
        "required": ["reason", "summary"],
    },
)
def escalate_to_human(session: Session, reason: str, summary: str) -> str:
    session.escalated = True
    ticket = "TKT-" + (session.verified_customer_id or "ANON")
    return ok(
        ticket_id=ticket,
        reason=reason,
        summary=summary,
        queue_position=3,
        expected_wait_minutes=6,
    )
