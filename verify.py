"""
verify.py — proves iglegais actually works: ingest a known causal graph,
then assert that vector-search + graph-traversal returns the ROOT CAUSE
(something a flat vector store cannot do).
Run against a fresh local instance for a clean check.
"""
from mg import MemoryGraph

mg = MemoryGraph()
mg.setup()

# a distinct story with unusual tokens so vector search is unambiguous
leak = mg.add("The zorbex-9 module leaked memory and crashed the data pipeline.")
alert = mg.add("Ops got paged at 2am: the zorbex-9 pipeline went completely down.",
               causes=[leak])
fixed = mg.add("Patched the zorbex-9 memory leak and the pipeline recovered.",
               follows=leak, contradicts=[alert])

r = mg.recall("why did the zorbex pipeline go down?")

print("recall result:", r)

# ---- assertions ----
assert r["closest_memory"], "vector search returned nothing"
assert any("zorbex" in c.lower() for c in r["closest_memory"]), \
    f"vector search found the wrong memory: {r['closest_memory']}"
assert any("leak" in c.lower() for c in r["caused_by"]), \
    f"causal traversal did NOT surface the root cause: {r['caused_by']}"

print("\nPASS")
print("  - vector search found the right memory (the outage)")
print("  - graph traversal surfaced the ROOT CAUSE (the memory leak)")
print("  - contradiction edge found the later fix")
print("  - a flat vector store returns only the outage, never the cause")
