"""
╔══════════════════════════════════════════════════════════════════════════╗
║  CUSTOMIZATION POINT  ·  tools/                                          ║
║                                                                          ║
║  Add a new tool by:                                                      ║
║    1.  Creating tools/<your_tool>.py                                     ║
║    2.  Decorating the implementation with @tool(...)                     ║
║    3.  Importing the module below so it registers at startup             ║
║                                                                          ║
║  That's it. The registry produces both the Gemini function declarations  ║
║  (for the model) and the Python dispatch table (for execution).          ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

from ._registry import (  # noqa: F401  (re-exported)
    tool,
    Session,
    dispatch,
    function_declarations,
    list_tool_names,
)

# Import each tool module so its @tool registration fires.
# To remove a tool from the agent, just comment it out here — no other
# changes needed.
from . import orders         # noqa: F401
from . import returns        # noqa: F401
from . import help_center    # noqa: F401
from . import escalation     # noqa: F401
