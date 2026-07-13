"""auto edge extraction.

asks an llm which prior memories a new memory caused_by / contradicts /
follows, so the graph builds itself from plain text.

set CEREBRAS_API_KEY in .env (or the environment). fast, no local model.
"""
import json
import os

from openai import OpenAI

BASE_URL = "https://api.cerebras.ai/v1"
MODEL = os.environ.get("IGLEGAIS_MODEL", "gpt-oss-120b")

PROMPT = """You connect memories into a causal graph.
Given a NEW memory and some CANDIDATE earlier memories, decide how the NEW
memory relates to each candidate. Allowed relations:
- caused_by: the candidate is the underlying CAUSE of the new memory
- contradicts: the new memory reverses or invalidates the candidate
- follows: the new memory happens after the candidate, same thread, no causation

Be strict. Only emit a relation you are confident about. A fix or a resolution
is NOT caused_by the problem it fixes. Most pairs have NO relation at all.
If unsure, leave it out.

Reply as JSON only:
{{"edges": [{{"id": <candidate id>, "rel": "caused_by|contradicts|follows"}}]}}

NEW: {new}
CANDIDATES:
{cands}
"""

_VALID = {"caused_by", "contradicts", "follows"}
_client = None


def _api_key() -> str | None:
    key = os.environ.get("CEREBRAS_API_KEY")
    if key:
        return key
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if line.startswith("CEREBRAS_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


def _get_client():
    global _client
    if _client is None:
        key = _api_key()
        if not key:
            return None
        _client = OpenAI(api_key=key, base_url=BASE_URL)
    return _client


def infer_edges(new_memory: str, candidates: list[dict], timeout: int = 60) -> list[dict]:
    """candidates: [{'id': int, 'content': str}]. returns [{'id', 'rel'}]."""
    if not candidates:
        return []
    client = _get_client()
    if client is None:
        return []

    cands = "\n".join(f"- id {c['id']}: {c['content']}" for c in candidates)
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "user", "content": PROMPT.format(new=new_memory, cands=cands)}
            ],
            temperature=0,
            response_format={"type": "json_object"},
            timeout=timeout,
        )
        edges = json.loads(resp.choices[0].message.content).get("edges", [])
    except Exception as e:
        print(f"[extract] llm call failed: {e}")
        return []

    cand_ids = {c["id"] for c in candidates}
    return [e for e in edges if e.get("rel") in _VALID and e.get("id") in cand_ids]
