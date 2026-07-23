"""local backend: the whole memory graph in a single sqlite file.

no server, no container, no network. memories are rows, edges are rows,
vector search is a numpy dot product over normalized embeddings. this is the
default backend so `pip install iglegais` just works with nothing else running.

same public surface as the server-backed graph: setup, add, recall, remember,
root_cause, _candidates.
"""
from __future__ import annotations

import os
import sqlite3
import time

import numpy as np

from .embedding import embed


def _db_path() -> str:
    p = os.environ.get("IGLEGAIS_DB")
    if not p:
        p = os.path.join(os.path.expanduser("~"), ".iglegais", "memory.db")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


class LocalMemoryGraph:
    def __init__(self, path: str | None = None, **_ignored):
        self.path = path or _db_path()
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._ensure()

    def _ensure(self):
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS memories("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "content TEXT NOT NULL, embedding BLOB NOT NULL, ts INTEGER NOT NULL)"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS edges("
            "src INTEGER NOT NULL, dst INTEGER NOT NULL, rel TEXT NOT NULL,"
            "UNIQUE(src, dst, rel))"
        )
        self.conn.commit()

    def setup(self):
        """schema is created on connect; here for parity with the server backend."""
        self._ensure()
        return {"ok": True}

    # ---- writes ----

    def _near_duplicate(self, content: str, threshold: float = 0.97) -> int | None:
        """id of an existing near identical memory, or None. embeddings are
        normalized so cosine similarity is the dot product."""
        top = self._search(content, 1)
        if top and top[0][0] >= threshold:
            return top[0][1]
        return None

    def add(self, content: str, causes: list[int] | None = None,
            contradicts: list[int] | None = None, follows: int | None = None,
            dedup: bool = False, dedup_threshold: float = 0.97) -> int:
        if dedup:
            existing = self._near_duplicate(content, dedup_threshold)
            if existing is not None:
                # reuse the existing node, but still wire any new edges to it
                self._link_new(existing, causes, contradicts, follows)
                return existing
        vec = np.asarray(embed(content), dtype=np.float32).tobytes()
        cur = self.conn.execute(
            "INSERT INTO memories(content, embedding, ts) VALUES(?, ?, ?)",
            (content, vec, int(time.time())),
        )
        nid = cur.lastrowid
        self._link_new(nid, causes, contradicts, follows)
        return nid

    def _link_new(self, src: int, causes, contradicts, follows):
        edges: list[tuple[str, int]] = []
        if follows is not None:
            edges.append(("FOLLOWS", follows))
        for c in (causes or []):
            edges.append(("CAUSED_BY", c))
        for c in (contradicts or []):
            edges.append(("CONTRADICTS", c))
        self._link(src, edges)
        self.conn.commit()

    def _link(self, src: int, edges: list[tuple[str, int]]):
        for rel, dst in edges:
            self.conn.execute(
                "INSERT OR IGNORE INTO edges(src, dst, rel) VALUES(?, ?, ?)",
                (src, dst, rel),
            )

    def remember(self, content: str, k: int = 6, dedup: bool = True):
        """add a memory and let the llm infer its edges to prior ones.
        dedup is on by default here: a near identical memory is reused, not
        stored twice."""
        from .extract import infer_edges

        cands = self._candidates(content, k)
        edges = infer_edges(content, cands)
        rel_map = {"caused_by": "CAUSED_BY", "contradicts": "CONTRADICTS", "follows": "FOLLOWS"}
        nid = self.add(content, dedup=dedup)
        self._link(nid, [(rel_map[e["rel"]], e["id"]) for e in edges if e["rel"] in rel_map])
        self.conn.commit()
        return nid, edges

    # ---- vector search ----

    def _search(self, query: str, k: int = 1):
        rows = self.conn.execute("SELECT id, content, embedding FROM memories").fetchall()
        if not rows:
            return []
        qv = np.asarray(embed(query), dtype=np.float32)
        scored = [
            (float(qv @ np.frombuffer(blob, dtype=np.float32)), rid, content)
            for rid, content, blob in rows
        ]
        scored.sort(key=lambda t: t[0], reverse=True)
        return scored[:k]

    def _candidates(self, text: str, k: int = 6):
        return [{"id": rid, "content": content} for _, rid, content in self._search(text, k)]

    # ---- reads ----

    def recall(self, query: str):
        top = self._search(query, 1)
        if not top:
            return {"closest_memory": [], "caused_by": [], "later_contradicted_by": []}
        _, hid, hcontent = top[0]
        caused = self.conn.execute(
            "SELECT m.content FROM edges e JOIN memories m ON m.id = e.dst "
            "WHERE e.src = ? AND e.rel = 'CAUSED_BY'", (hid,)
        ).fetchall()
        contra = self.conn.execute(
            "SELECT m.content FROM edges e JOIN memories m ON m.id = e.src "
            "WHERE e.dst = ? AND e.rel = 'CONTRADICTS'", (hid,)
        ).fetchall()
        return {
            "closest_memory": [hcontent],
            "caused_by": [r[0] for r in caused],
            "later_contradicted_by": [r[0] for r in contra],
            # temporal: is this belief still current, or did a newer memory retract it?
            "status": "retracted" if contra else "current",
        }

    # ---- temporal: what is still true ----

    def _ts(self, nid: int):
        row = self.conn.execute("SELECT ts FROM memories WHERE id = ?", (nid,)).fetchone()
        return row[0] if row else None

    def _contradictors(self, nid: int, as_of: int | None = None):
        """memories that contradict nid. with as_of, only those that existed by then."""
        q = ("SELECT m.id, m.content, m.ts FROM edges e JOIN memories m ON m.id = e.src "
             "WHERE e.dst = ? AND e.rel = 'CONTRADICTS'")
        params: list = [nid]
        if as_of is not None:
            q += " AND m.ts <= ?"
            params.append(as_of)
        return self.conn.execute(q, params).fetchall()

    def is_current(self, nid: int, as_of: int | None = None) -> bool:
        """current = nothing (that existed by as_of) contradicts it."""
        return not self._contradictors(nid, as_of)

    def what_is_true(self, query: str, as_of: int | None = None, k: int = 8):
        """current-truth recall: the best matching memory that a newer memory has
        NOT retracted. with as_of (unix seconds), answers what was true then.

        a flat vector store cannot do this: it has no notion of one memory
        invalidating another over time, so it happily returns the stale belief.
        """
        ranked = self._search(query, k)
        retracted = []
        for _, nid, content in ranked:
            if as_of is not None and self._ts(nid) > as_of:
                continue  # this memory did not exist yet at as_of
            if self.is_current(nid, as_of):
                return {
                    "answer": content,
                    "memory_id": nid,
                    "status": "current",
                    "retracted_alternatives": retracted,
                }
            retracted.append(content)
        return {"answer": None, "status": "no_current_match", "retracted_alternatives": retracted}

    def root_cause(self, query: str, max_depth: int = 6):
        """walk the caused_by chain from the closest memory down to the root."""
        top = self._search(query, 1)
        if not top:
            return []
        _, hid, hcontent = top[0]
        chain = [hcontent]
        seen = {hid}
        cur = hid
        for _ in range(max_depth):
            row = self.conn.execute(
                "SELECT m.id, m.content FROM edges e JOIN memories m ON m.id = e.dst "
                "WHERE e.src = ? AND e.rel = 'CAUSED_BY' LIMIT 1", (cur,)
            ).fetchone()
            if not row or row[0] in seen:
                break
            seen.add(row[0])
            chain.append(row[1])
            cur = row[0]
        return chain
