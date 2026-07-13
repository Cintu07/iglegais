"""auto extraction test.

the whole point: we pass PLAIN TEXT with no manual edges. the local llm has to
figure out the caused_by / contradicts / follows links itself. then recall
should still be able to walk to the root cause.
"""
from mg import MemoryGraph

mg = MemoryGraph()
mg.setup()

facts = [
    "the deploy script had a race condition between two workers.",
    "the race condition corrupted the shared config file.",
    "the service failed to boot after the nightly restart.",
    "we added a lock to the deploy script and the service boots fine now.",
]

print("ingesting plain text, no manual edges. llm infers the graph:\n")
for f in facts:
    nid, edges = mg.remember(f)
    print(f"  [{nid}] {f}")
    for e in edges:
        print(f"        -> inferred {e['rel']} -> id {e['id']}")

print("\n" + "=" * 60)
r = mg.recall("why did the service fail to boot?")
print("Q: why did the service fail to boot?")
print(f"  memory:     {r['closest_memory']}")
print(f"  caused by:  {r['caused_by']}")
print(f"  contradicted by: {r['later_contradicted_by']}")

chain = mg.root_cause("why did the service fail to boot?")
print(f"\n  full chain: {chain}")

got_edges = bool(r["caused_by"]) or len(chain) > 0
print("\n" + ("PASS: the llm built the causal graph from plain text on its own"
             if got_edges else
             "FAIL: no edges were inferred (model may need a better prompt or a bigger model)"))
