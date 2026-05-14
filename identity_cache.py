"""
╔══════════════════════════════════════════════════════════════════════════╗
║  Server-side identity cache.                                             ║
║                                                                          ║
║  DEMO SCOPE: single-process, single-customer.                            ║
║                                                                          ║
║  - Written only by a successful verify_customer call (see                ║
║    tools/orders.py). The browser never writes to this cache.             ║
║  - Read by BooklyLiveAgent.__init__ when a new Session is created,       ║
║    so a returning user (browser refresh, new tab) doesn't have to        ║
║    re-verify.                                                            ║
║  - Cleared on server restart. That's a feature, not a bug — it           ║
║    bounds the trust window for the demo.                                 ║
║                                                                          ║
║  Why not store this on the client?                                       ║
║    Because identity must be enforced server-side. If the client tells    ║
║    the server "I'm C-1001", anyone editing localStorage becomes          ║
║    C-1001. The whole point of the verify_customer tool is to make the    ║
║    server the source of truth.                                           ║
║                                                                          ║
║  Production path: replace this with a short-lived, encrypted,            ║
║  server-issued token. The browser holds an opaque cookie/header; the     ║
║  server keeps the (token → customer_id) map. Same `record` / `hydrate`   ║
║  surface, different backing store.                                       ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tools._registry import Session


# Module-private. Use record() / hydrate() — don't touch directly.
_CACHE: dict[str, str] | None = None


def record(email: str, customer_id: str) -> None:
    """Called by verify_customer after a successful identity check.

    Overwrites any prior entry — single-customer demo assumption. If two
    different customers verify on the same server process, the second
    wins. Documented and intentional for the take-home.
    """
    global _CACHE
    _CACHE = {"email": email, "customer_id": customer_id}


def hydrate(session: "Session") -> bool:
    """Apply the cached identity to a fresh Session, if any.

    Returns True if the session was hydrated, False otherwise. Never
    overwrites an already-verified session — that would let a later
    verify_customer call get clobbered by the cache on the next message.
    """
    if not _CACHE:
        return False
    if session.is_verified():
        return False
    session.verified_email = _CACHE["email"]
    session.verified_customer_id = _CACHE["customer_id"]
    return True


def clear() -> None:
    """Wipe the cache. Exposed for tests; not called in normal operation."""
    global _CACHE
    _CACHE = None
