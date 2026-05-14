"""
Tool registry — internal plumbing. You probably don't need to edit this
file; edit the individual tool modules in tools/ or add new ones.

The @tool decorator captures:
  - the function (for dispatch)
  - a Gemini-format FunctionDeclaration (for the model)

Sessions are per-conversation state. Tools take a Session as their first
argument so they can enforce gates like "must be verified before order
lookup." That's the single biggest hallucination-prevention lever: the
model can't bypass a check that lives in your code.
"""

from __future__ import annotations

import json
from typing import Any, Callable


# ────────────────────────────────────────────────────────────────────────── #
#  Session — the agent's working memory.                                    #
# ────────────────────────────────────────────────────────────────────────── #
class Session:
    """Per-conversation state passed to every tool call."""

    def __init__(self) -> None:
        self.verified_email: str | None = None
        self.verified_customer_id: str | None = None
        self.last_order_id: str | None = None
        self.failed_turns: int = 0
        self.escalated: bool = False

    def is_verified(self) -> bool:
        return self.verified_customer_id is not None


# ────────────────────────────────────────────────────────────────────────── #
#  Registry                                                                 #
# ────────────────────────────────────────────────────────────────────────── #
_TOOLS: dict[str, Callable[..., str]] = {}
_DECLARATIONS: list[dict[str, Any]] = []


def tool(
    *,
    name: str,
    description: str,
    parameters: dict[str, Any],
) -> Callable[[Callable[..., str]], Callable[..., str]]:
    """Register a function as a Bookly tool.

    `parameters` is a Gemini-style JSON schema (TYPE names UPPERCASE).
    The wrapped function must accept `(session: Session, **kwargs) -> str`
    and return a JSON-encoded string.
    """

    def decorate(fn: Callable[..., str]) -> Callable[..., str]:
        if name in _TOOLS:
            raise RuntimeError(f"Tool {name!r} already registered")
        _TOOLS[name] = fn
        _DECLARATIONS.append(
            {
                "name": name,
                "description": description,
                "parameters": parameters,
            }
        )
        return fn

    return decorate


def list_tool_names() -> list[str]:
    return list(_TOOLS.keys())


def function_declarations() -> list[dict[str, Any]]:
    """Return the tool list in the shape Gemini's Live API expects."""
    return list(_DECLARATIONS)


def dispatch(session: Session, name: str, args: dict[str, Any]) -> str:
    fn = _TOOLS.get(name)
    if not fn:
        return json.dumps(
            {"ok": False, "error_code": "unknown_tool", "message": f"No tool {name!r}"}
        )
    try:
        return fn(session, **args)
    except TypeError as e:
        return json.dumps(
            {"ok": False, "error_code": "bad_args", "message": str(e)}
        )


# ────────────────────────────────────────────────────────────────────────── #
#  Response helpers used by tool implementations.                           #
# ────────────────────────────────────────────────────────────────────────── #
def ok(**payload: Any) -> str:
    return json.dumps({"ok": True, **payload}, default=str)


def err(code: str, message: str) -> str:
    return json.dumps({"ok": False, "error_code": code, "message": message})
