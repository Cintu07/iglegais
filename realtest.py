"""
realtest.py — a real-world test: a 2-week engineering incident log with TWO
separate incidents (an auth outage and a caching bug). The hard part is
discrimination: given a mixed graph, does iglegais find the RIGHT memory and
attribute the RIGHT cause to each symptom, without mixing them up?
"""
from mg import MemoryGraph

mg = MemoryGraph()
mg.setup()

# ---- incident 1: auth migration causes logouts ----
migrate = mg.add("May 2: migrated the auth service to a new JWT library.")
logouts = mg.add("May 3: users reported getting randomly logged out every few minutes.",
                 causes=[migrate])
expiry = mg.add("May 3: found the new JWT library defaults token expiry to 5 minutes.",
                causes=[migrate])
authfix = mg.add("May 4: set JWT expiry to 24 hours and redeployed.", follows=expiry)
authok = mg.add("May 4: the random logout reports stopped.", follows=authfix,
                contradicts=[logouts])

# ---- incident 2 (unrelated): caching causes stale data ----
cache = mg.add("May 10: enabled a new caching layer to speed up the dashboard.")
stale = mg.add("May 11: the dashboard showed stale, out-of-date numbers for some users.",
               causes=[cache])
cachefix = mg.add("May 12: added cache invalidation on write and the stale data went away.",
                  follows=cache, contradicts=[stale])


def ask(q):
    r = mg.recall(q)
    print(f"\nQ: {q}")
    print(f"   memory:      {r['closest_memory']}")
    print(f"   root cause:  {r['caused_by']}")
    if r["later_contradicted_by"]:
        print(f"   resolved by: {r['later_contradicted_by']}")


ask("why were users getting logged out?")
ask("why was the dashboard showing old numbers?")

# ---- the discrimination check ----
r1 = mg.recall("why were users getting logged out?")
r2 = mg.recall("why was the dashboard showing old numbers?")
ok1 = any("jwt" in c.lower() or "expiry" in c.lower() or "auth" in c.lower()
          for c in r1["caused_by"])
ok2 = any("cach" in c.lower() for c in r2["caused_by"])
print("\n" + "=" * 55)
print("DISCRIMINATION TEST (two incidents, right cause each):")
print(f"  logout question  -> auth/JWT cause?   {'PASS' if ok1 else 'FAIL'}")
print(f"  stale-data question -> caching cause? {'PASS' if ok2 else 'FAIL'}")
print("  " + ("BOTH PASS: it kept the incidents straight." if ok1 and ok2
              else "one crossed wires."))
