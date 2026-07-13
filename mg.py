"""
mg — a causal/temporal memory graph on HelixDB.

The idea: memories are NODES with vector embeddings AND typed edges
(CAUSED_BY, CONTRADICTS, FOLLOWS). Recall does what a flat vector store
can't: vector-search to the relevant memory, then TRAVERSE the graph to
return *why* it happened / how it evolved.

Runs against a local graph+vector instance on localhost:6969.
"""
from __future__ import annotations
import sys, os, time

# use the local graph+vector python SDK (vendored alongside this project)
SDK = os.path.join(os.path.dirname(__file__), "..", "helixdb", "sdks", "python", "src")
sys.path.insert(0, os.path.abspath(SDK))

from helixdb import (  # noqa: E402
    Client, DynamicQueryRequest, g, read_batch, write_batch,
    Step, Traversal, NodeRef, RepeatConfig, sub, Projection,
)
from sentence_transformers import SentenceTransformer  # noqa: E402

URL = "http://localhost:6969"
_model = SentenceTransformer("all-MiniLM-L6-v2")  # 384-dim, local


def embed(text: str) -> list[float]:
    return _model.encode(text, normalize_embeddings=True).tolist()


class MemoryGraph:
    def __init__(self, url: str = URL):
        self.client = Client(url)

    def _write(self, batch):
        return self.client.query().dynamic(DynamicQueryRequest.write(batch)).send()

    def _read(self, batch):
        return self.client.query().dynamic(DynamicQueryRequest.read(batch)).send()

    def setup(self):
        """Create the vector index on Memory.embedding."""
        batch = write_batch().var_as(
            "idx",
            Traversal.from_steps(
                [Step.create_vector_index_nodes("Memory", "embedding", None)],
                state="terminal", mode="write",
            ),
        ).returning(["idx"])
        return self._write(batch)

    def add(self, content: str, causes: list[int] | None = None,
            contradicts: list[int] | None = None, follows: int | None = None) -> int:
        """Add a memory node, then link causal/temporal edges to prior memories."""
        props = {"content": content, "embedding": embed(content), "ts": int(time.time())}
        res = self._write(
            write_batch().var_as("m", g().add_n("Memory", props)).returning(["m"])
        )
        nid = _node_id(res, "m")
        edges = []
        if follows is not None:
            edges.append(("FOLLOWS", follows))
        for c in (causes or []):
            edges.append(("CAUSED_BY", c))
        for c in (contradicts or []):
            edges.append(("CONTRADICTS", c))
        for label, target in edges:
            self._write(
                write_batch().var_as(
                    "e", g().n(NodeRef.id(nid)).add_e(label, NodeRef.id(target), {})
                ).returning(["e"])
            )
        return nid

    def recall(self, query: str):
        """Vector-search the closest memory, then traverse its causal chain.
        Returns readable content for both the hit and its cause(s)."""
        qv = embed(query)
        hit = self._read(
            read_batch().var_as(
                "hit",
                g().vector_search_nodes("Memory", "embedding", qv, 1).value_map(["content"]),
            ).returning(["hit"])
        )
        why = self._read(
            read_batch().var_as(
                "why",
                g().vector_search_nodes("Memory", "embedding", qv, 1)
                .out("CAUSED_BY").value_map(["content"]),
            ).returning(["why"])
        )
        contra = self._read(
            read_batch().var_as(
                "c",
                g().vector_search_nodes("Memory", "embedding", qv, 1)
                .in_("CONTRADICTS").value_map(["content"]),
            ).returning(["c"])
        )
        return {
            "closest_memory": _contents(hit, "hit"),
            "caused_by": _contents(why, "why"),
            "later_contradicted_by": _contents(contra, "c"),
        }

    def _candidates(self, text: str, k: int = 6):
        """top-k vector-similar prior memories, with ids, as edge candidates."""
        qv = embed(text)
        res = self._read(
            read_batch().var_as(
                "cand",
                g().vector_search_nodes("Memory", "embedding", qv, k).project(
                    [Projection.property("$id", "id"), Projection.property("content", "content")]
                ),
            ).returning(["cand"])
        )
        rows = []

        def walk(x):
            if isinstance(x, dict):
                if "id" in x and "content" in x:
                    rows.append({"id": x["id"], "content": x["content"]})
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)

        walk(res)
        return rows

    def remember(self, content: str, k: int = 6):
        """add a memory and let the local llm infer its edges to prior ones.
        this is the self-building version: you pass plain text, no manual edges."""
        from extract import infer_edges

        cands = self._candidates(content, k)
        edges = infer_edges(content, cands)
        rel_map = {"caused_by": "CAUSED_BY", "contradicts": "CONTRADICTS", "follows": "FOLLOWS"}

        props = {"content": content, "embedding": embed(content), "ts": int(time.time())}
        res = self._write(
            write_batch().var_as("m", g().add_n("Memory", props)).returning(["m"])
        )
        nid = _node_id(res, "m")
        for e in edges:
            label = rel_map.get(e["rel"])
            if not label:
                continue
            self._write(
                write_batch().var_as(
                    "e", g().n(NodeRef.id(nid)).add_e(label, NodeRef.id(e["id"]), {})
                ).returning(["e"])
            )
        return nid, edges

    def root_cause(self, query: str, max_depth: int = 6):
        """Walk the FULL caused_by chain (symptom -> cause -> deeper cause ->
        root), not just one hop. The last link is the root cause."""
        qv = embed(query)
        chain = self._read(
            read_batch().var_as(
                "chain",
                g().vector_search_nodes("Memory", "embedding", qv, 1)
                .repeat(RepeatConfig.new(sub().out("CAUSED_BY")).emit_all().max_depth(max_depth))
                .value_map(["content"]),
            ).returning(["chain"])
        )
        return _contents(chain, "chain")


def _node_id(result, var):
    """Pull the created node id out of a write result: {'m': {'ids': [1]}}."""
    try:
        return result[var]["ids"][0]
    except Exception:
        return None


def _contents(result, var):
    """Recursively pull every 'content' string out of a value_map result."""
    out = []

    def walk(x):
        if isinstance(x, dict):
            if isinstance(x.get("content"), str):
                out.append(x["content"])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(result.get(var, result) if isinstance(result, dict) else result)
    return out


if __name__ == "__main__":
    mg = MemoryGraph()
    print("setup:", mg.setup())
    # a small causal story (customer support arc)
    m_bug = mg.add("A retry bug double-charged some customers in March.")
    m_complaint = mg.add("March 3: a customer said their card was charged twice.",
                         causes=[m_bug])
    m_fix = mg.add("March 5: refunded the customer and shipped a fix for the retry bug.",
                   follows=m_bug)
    m_happy = mg.add("March 20: the same customer said they love the service now.",
                     follows=m_fix, contradicts=[m_complaint])
    q = "why was the customer upset about billing?"
    r = mg.recall(q)
    print("\n" + "=" * 60)
    print(f"Q: {q}")
    print("=" * 60)
    print(f"closest memory (vector search):\n   {r['closest_memory']}")
    print(f"\nWHY — caused by (graph traversal):\n   {r['caused_by']}")
    print("\n(a flat vector store returns only the first line; the graph")
    print(" traversal is what surfaces the *cause*.)")
