"""
Mock backend. In production these would be three different systems:
  - Orders DB (Postgres)
  - Returns service (RMA system)
  - Help-center CMS (with a vector index)

For the prototype we keep them as in-memory dicts. Tool implementations
in tools/ should be ported 1:1 to live endpoints when promoting.
"""

from datetime import datetime, timedelta

TODAY = datetime(2026, 5, 12)


CUSTOMERS = {
    "john@myspace.com": {"name": "John Stewart", "customer_id": "C-1001"},
    "jimmy@hotmail.com":   {"name": "Jimmy Kimmel",   "customer_id": "C-1002"},
}


ORDERS = {
    "BK-48201": {
        "customer_id": "C-1001",
        "placed_at": TODAY - timedelta(days=4),
        "status": "shipped",
        "carrier": "UPS",
        "tracking": "1Z999AA10123456784",
        "eta": TODAY + timedelta(days=2),
        "items": [
            {"item_id": "I-1", "title": "The Pragmatic Programmer", "qty": 1, "price": 39.99},
            {"item_id": "I-2", "title": "Designing Data-Intensive Applications", "qty": 1, "price": 54.00},
        ],
    },
    "BK-48199": {
        "customer_id": "C-1001",
        "placed_at": TODAY - timedelta(days=45),
        "status": "delivered",
        "carrier": "USPS",
        "tracking": "9400111899223197654321",
        "eta": TODAY - timedelta(days=40),
        "items": [
            {"item_id": "I-3", "title": "Atomic Habits", "qty": 2, "price": 18.50},
        ],
    },
    "BK-49000": {
        "customer_id": "C-1002",
        "placed_at": TODAY - timedelta(days=1),
        "status": "processing",
        "carrier": None,
        "tracking": None,
        "eta": TODAY + timedelta(days=5),
        "items": [
            {"item_id": "I-4", "title": "Sapiens", "qty": 1, "price": 22.00},
        ],
    },
}


FAQ = [
    {
        "id": "faq-shipping",
        "title": "Shipping times and costs",
        "keywords": ["shipping", "delivery", "ship", "how long", "arrive"],
        "body": (
            "Bookly ships within 1 business day. Standard shipping is "
            "$3.99 (3–5 business days) and free on orders over $35. "
            "Expedited shipping is $9.99 (2 business days)."
        ),
    },
    {
        "id": "faq-password",
        "title": "Resetting your password",
        "keywords": ["password", "reset", "login", "sign in", "forgot"],
        "body": (
            "To reset your password, visit bookly.example/account/reset "
            "and enter the email on your account. The reset link expires "
            "in 30 minutes."
        ),
    },
    {
        "id": "faq-returns",
        "title": "Return policy basics",
        "keywords": ["return", "refund", "policy", "send back"],
        "body": (
            "Most physical books can be returned within 30 days of "
            "delivery if unused and in original packaging. Digital books "
            "and gift cards are non-returnable. Refunds are issued to the "
            "original payment method within 5 business days of receipt."
        ),
    },
    {
        "id": "faq-cancel",
        "title": "Cancelling an order",
        "keywords": ["cancel", "stop order", "change order"],
        "body": (
            "Orders can be cancelled for a full refund any time before "
            "they enter 'shipped' status. Once shipped, please initiate "
            "a return after delivery."
        ),
    },
    {
        "id": "faq-gift",
        "title": "Gift orders",
        "keywords": ["gift", "wrap", "message", "present"],
        "body": (
            "Add gift wrapping ($3.50) and a message at checkout. Gift "
            "orders ship without a price on the packing slip."
        ),
    },
]
