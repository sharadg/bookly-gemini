"""
Order-related tools: identity verification and order lookup.

To add a tool in this family:
    @tool(name="...", description="...", parameters={...})
    def my_tool(session, **kwargs) -> str:
        ...
        return ok(...) or err(...)
"""

from __future__ import annotations

from data import CUSTOMERS, ORDERS
from ._registry import Session, tool, ok, err


@tool(
    name="verify_customer",
    description=(
        "Verify the customer's identity using the email on their Bookly "
        "account. Call this BEFORE any tool that accesses order-specific "
        "data. If the customer has not given an email yet, ask them for "
        "it first — do not guess."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "email": {
                "type": "STRING",
                "description": "Email address the customer provides.",
            }
        },
        "required": ["email"],
    },
)
def verify_customer(session: Session, email: str) -> str:
    email = email.strip().lower()
    customer = CUSTOMERS.get(email)
    if not customer:
        return err(
            "not_found",
            "No Bookly account matches that email. Ask the customer to "
            "double-check the spelling.",
        )
    session.verified_email = email
    session.verified_customer_id = customer["customer_id"]
    return ok(customer_name=customer["name"], verified=True)


@tool(
    name="lookup_order",
    description=(
        "Fetch order status, items, carrier, tracking, and ETA. Requires "
        "the customer to be verified first via verify_customer. Returns "
        "an error if the order does not belong to the verified customer."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "order_id": {
                "type": "STRING",
                "description": "Order ID, e.g. BK-48201.",
            }
        },
        "required": ["order_id"],
    },
)
def lookup_order(session: Session, order_id: str) -> str:
    if not session.is_verified():
        return err(
            "not_verified",
            "Customer must be verified via verify_customer before "
            "order details can be disclosed.",
        )
    order = ORDERS.get(order_id)
    # Don't leak existence to a non-owner — same shape as not_found.
    if not order or order["customer_id"] != session.verified_customer_id:
        return err("not_found", f"No order found with id {order_id}.")
    session.last_order_id = order_id
    return ok(
        order_id=order_id,
        placed_at=order["placed_at"].date().isoformat(),
        status=order["status"],
        carrier=order["carrier"],
        tracking=order["tracking"],
        eta=order["eta"].date().isoformat() if order["eta"] else None,
        items=order["items"],
    )
