"""iglegais mcp server.

exposes the memory graph as tools so any mcp client (claude, cursor, etc.)
can store memories and ask why things happened. needs a local graph+vector
instance running on localhost:6969.
"""
from mcp.server.fastmcp import FastMCP
from mg import MemoryGraph

mcp = FastMCP("iglegais")
_mg = None


def graph() -> MemoryGraph:
    global _mg
    if _mg is None:
        _mg = MemoryGraph()
        _mg.setup()
    return _mg


@mcp.tool()
def remember(content: str) -> str:
    """Store a memory for later recall."""
    nid = graph().add(content)
    return f"remembered (id {nid})"


@mcp.tool()
def recall(query: str) -> dict:
    """Recall the closest memory, plus its cause and any later contradiction."""
    return graph().recall(query)


@mcp.tool()
def why(query: str) -> list[str]:
    """Trace the full root cause chain for a question, symptom down to root."""
    return graph().root_cause(query)


if __name__ == "__main__":
    mcp.run()
