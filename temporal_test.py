"""temporal test: memory that knows what is still true.

the case a flat vector store cannot handle: a fact gets recorded, then a later
memory contradicts it. asked "what is true now", similarity search returns the
stale belief (it is still highly similar to the query). iglegais returns the
current truth and can also reconstruct what was true at an earlier moment.
"""
import os
import tempfile

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ["IGLEGAIS_DB"] = os.path.join(tempfile.mkdtemp(), "temporal.db")

from iglegais import LocalMemoryGraph

fails = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


mg = LocalMemoryGraph()
mg.setup()

# a belief, then its later retraction. we control timestamps so as_of is exact.
old = mg.add("the primary database is postgres")
mg.conn.execute("UPDATE memories SET ts = 1000 WHERE id = ?", (old,))
new = mg.add("we migrated the primary database from postgres to mysql", contradicts=[old])
mg.conn.execute("UPDATE memories SET ts = 2000 WHERE id = ?", (new,))
mg.conn.commit()

# 1. current truth: must return mysql, not the stale postgres line.
print("1. what is true now")
now = mg.what_is_true("what is the primary database?")
check("returns the current truth (mysql)", "mysql" in (now["answer"] or ""), f"got '{now['answer']}'")
check("status is current", now["status"] == "current")
check("names the retracted belief", any("postgres" in r for r in now["retracted_alternatives"]))

# 2. flat vector search returns the STALE belief (the thing we beat).
print("2. flat vector search returns the stale answer")
flat_top1 = mg._search("what is the primary database?", 1)[0][2]
check("flat top-1 is the old postgres line (stale)", "postgres" in flat_top1 and "mysql" not in flat_top1,
      f"got '{flat_top1}'")

# 3. as-of query: what was true BEFORE the migration (t=1500).
print("3. point-in-time: what was true at t=1500 (before migration)")
past = mg.what_is_true("what is the primary database?", as_of=1500)
check("as-of returns postgres (true back then)", "postgres" in (past["answer"] or ""), f"got '{past['answer']}'")

# 4. recall surfaces the retracted status of the old memory.
print("4. recall marks the retracted belief")
r = mg.recall("the primary database is postgres")
check("old belief marked retracted", r["status"] == "retracted", f"status={r['status']}")

# 5. an uncontradicted fact stays current.
print("5. uncontradicted fact is current")
mg.add("the cache layer is redis")
r2 = mg.recall("what is the cache layer?")
check("redis fact is current", r2["status"] == "current")

print()
if fails:
    print(f"FAILED ({len(fails)}): " + ", ".join(fails))
    raise SystemExit(1)
print("ALL TEMPORAL TESTS PASSED")
