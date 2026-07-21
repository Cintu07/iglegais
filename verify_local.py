"""verify the local sqlite backend end to end. no server, no container.

same test as verify.py, but against the zero-dependency backend: store a small
incident story with causal edges, then show that recall walks the graph to the
ROOT CAUSE, which a flat vector store cannot do.
"""
import os
import tempfile

# isolated throwaway db so the test never touches your real memories
os.environ["IGLEGAIS_DB"] = os.path.join(tempfile.mkdtemp(), "verify.db")

from iglegais import LocalMemoryGraph

mg = LocalMemoryGraph()
mg.setup()

leak = mg.add("the image service leaked memory on every upload.")
oom = mg.add("the box ran out of memory and the kernel killed the service.", causes=[leak])
outage = mg.add("users could not load their photos during the friday outage.", causes=[oom])
fix = mg.add("shipped a fix that frees the buffer after each upload.",
             follows=leak, contradicts=[leak])

q = "why was there a photo outage on friday?"
r = mg.recall(q)
chain = mg.root_cause(q)

ok = (
    r["closest_memory"] and "outage" in r["closest_memory"][0]
    and any("out of memory" in c for c in r["caused_by"])
    and any("leaked memory" in c for c in chain)
)

print("closest memory :", r["closest_memory"])
print("caused by      :", r["caused_by"])
print("root cause chain:", chain)
print("contradicted by :", r["later_contradicted_by"])
print()
if ok:
    print("PASS")
    print("  - vector search found the outage")
    print("  - graph traversal walked outage -> oom -> the memory leak (root cause)")
    print("  - all in one local sqlite file, nothing running")
else:
    print("FAIL")
    raise SystemExit(1)
