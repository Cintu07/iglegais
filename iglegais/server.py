"""iglegais mcp server.

exposes the memory graph as tools so any mcp client (claude, cursor, etc.)
can store memories and ask why things happened. needs a local graph+vector
instance running on localhost:6969.
"""
from mcp.server.fastmcp import FastMCP

from .mg import MemoryGraph

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
    """Store a memory. Causal links to earlier memories are inferred automatically."""
    nid, edges = graph().remember(content)
    if edges:
        rels = ", ".join(f"{e['rel']} -> {e['id']}" for e in edges)
        return f"remembered (id {nid}, linked: {rels})"
    return f"remembered (id {nid})"


@mcp.tool()
def recall(query: str) -> dict:
    """Recall the closest memory, plus its cause and any later contradiction."""
    return graph().recall(query)


@mcp.tool()
def why(query: str) -> list[str]:
    """Trace the full root cause chain for a question, symptom down to root."""
    return graph().root_cause(query)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
