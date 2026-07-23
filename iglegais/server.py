"""iglegais mcp server.

exposes the memory graph as tools so any mcp client (claude, cursor, etc.)
can store memories and ask why things happened.

by default everything lives in a single local sqlite file (nothing to run).
set IGLEGAIS_BACKEND=helix to use a graph+vector server instead (HELIX_URL,
default http://localhost:6969).
"""
import os

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("iglegais")
_mg = None


def graph():
    global _mg
    if _mg is None:
        if os.environ.get("IGLEGAIS_BACKEND", "local").lower() == "helix":
            from .home import helix_url
            from .mg import MemoryGraph

            _mg = MemoryGraph(url=helix_url())
        else:
            from .local import LocalMemoryGraph

            _mg = LocalMemoryGraph()
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


@mcp.tool()
def whats_true(query: str) -> dict:
    """What is currently true about this, ignoring beliefs a newer memory retracted."""
    g = graph()
    if not hasattr(g, "what_is_true"):
        return {"error": "temporal recall needs the local backend"}
    return g.what_is_true(query)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
