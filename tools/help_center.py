"""
Help-center retrieval. In production this is a vector store over the
CMS; here it's keyword scoring so the prototype has zero deps.

To replace with real retrieval:
    - Swap the body of search_help_center() to call your retriever.
    - Keep the return shape ({results: [{id, title, body}, ...]}) so the
      rest of the agent doesn't change.
"""

from __future__ import annotations

from data import FAQ
from ._registry import Session, tool, ok


@tool(
    name="search_help_center",
    description=(
        "Search Bookly's help center for general questions about "
        "shipping, policies, account management, etc. Use this for "
        "anything that is NOT specific to a customer's order. Returns "
        "up to 3 articles; quote from them, don't paraphrase."
    ),
    parameters={
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING"},
        },
        "required": ["query"],
    },
)
def search_help_center(session: Session, query: str) -> str:
    q = query.lower()
    scored = []
    for article in FAQ:
        score = sum(1 for kw in article["keywords"] if kw in q)
        if score > 0:
            scored.append((score, article))
    scored.sort(key=lambda x: -x[0])
    top = [
        {"id": a["id"], "title": a["title"], "body": a["body"]}
        for _, a in scored[:3]
    ]
    if not top:
        return ok(results=[], note="No matching articles found.")
    return ok(results=top)
