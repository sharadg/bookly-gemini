"""
Return / refund tools. Policy constants come from config.py — change
them there, not here, and the model will see consistent answers.
"""

from __future__ import annotations

import json

import config
from data import ORDERS, TODAY
from ._registry import Session, tool, ok, err


@tool(
    name="get_return_eligibility",
    description=(
        "Check whether a specific item in an order is eligible for "
        "return under Bookly's return policy. Returns a structured "
        "verdict (eligible, reason). NEVER answer return-policy "
        "questions about a specific item without calling this — the "
        "policy is the source of truth, not your prior knowledge."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "order_id": {"type": "STRING"},
            "item_id": {
                "type": "STRING",
                "description": "Item ID from the order's items list.",
            },
        },
        "required": ["order_id", "item_id"],
    },
)
def get_return_eligibility(session: Session, order_id: str, item_id: str) -> str:
    if not session.is_verified():
        return err("not_verified", "Customer must be verified first.")
    order = ORDERS.get(order_id)
    if not order or order["customer_id"] != session.verified_customer_id:
        return err("not_found", f"No order found with id {order_id}.")
    item = next((i for i in order["items"] if i["item_id"] == item_id), None)
    if not item:
        return err("not_found", f"Item {item_id} is not in order {order_id}.")

    days_since = (TODAY - order["placed_at"]).days
    window = config.RETURN_WINDOW_DAYS
    if days_since > window:
        return ok(
            eligible=False,
            reason=(
                f"This order was placed {days_since} days ago, which "
                f"is outside our {window}-day return window."
            ),
            item=item,
        )
    return ok(
        eligible=True,
        reason=(
            f"Within the {window}-day return window "
            f"({days_since} days since order)."
        ),
        item=item,
        condition_required=config.CONDITION_REQUIRED,
    )


@tool(
    name="submit_return",
    description=(
        "File a return request for an eligible item. Only call after "
        "get_return_eligibility returned eligible=true AND the customer "
        "has explicitly confirmed they want to return the item. Returns "
        "an RMA number on success."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "order_id": {"type": "STRING"},
            "item_id": {"type": "STRING"},
            "reason": {
                "type": "STRING",
                "description": "Customer-stated reason for the return.",
            },
        },
        "required": ["order_id", "item_id", "reason"],
    },
)
def submit_return(session: Session, order_id: str, item_id: str, reason: str) -> str:
    # Re-check eligibility server-side. The model can't decide eligibility.
    raw = get_return_eligibility(session, order_id=order_id, item_id=item_id)
    parsed = json.loads(raw)
    if not parsed.get("ok"):
        return raw
    if not parsed.get("eligible"):
        return err("not_eligible", parsed["reason"])

    rma = f"RMA-{order_id[-5:]}-{item_id[-1:]}"
    return ok(
        rma_number=rma,
        instructions=(
            f"We've emailed a prepaid return label to "
            f"{session.verified_email}. Drop the package at any UPS "
            f"location within 14 days. Refund posts within "
            f"{config.REFUND_BUSINESS_DAYS} business days of receipt."
        ),
        reason_recorded=reason,
    )
