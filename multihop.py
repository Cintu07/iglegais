"""multihop test: a 3-level causal chain. root_cause() should walk all the
way to the root, not stop at the first cause."""
from mg import MemoryGraph

mg = MemoryGraph()
mg.setup()

root = mg.add("the deploy script had a race condition between two workers.")
mid = mg.add("the race condition corrupted the shared config file.", causes=[root])
symptom = mg.add("the service failed to boot after the nightly restart.", causes=[mid])

chain = mg.root_cause("why did the service fail to boot?")
print("full causal chain (symptom -> ... -> root):")
for i, c in enumerate(chain):
    print(f"  {i}. {c}")

reached_root = any("race condition" in c.lower() and "deploy" in c.lower() for c in chain)
print("\n" + ("PASS: walked all the way to the root cause (the deploy race condition)"
             if reached_root else "did not reach the root"))
print(f"(chain length: {len(chain)})")
