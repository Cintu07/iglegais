"""brutal test suite for the local engine. no server, no mercy.

the point is to try to BREAK iglegais: infinite loops, cross-incident
contamination under noise, deep chains, persistence across reopen, self loops,
unicode, and scale. every case asserts. exit non-zero on any failure.
"""
import os
import tempfile
import time

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

WORKDIR = tempfile.mkdtemp()
os.environ["IGLEGAIS_DB"] = os.path.join(WORKDIR, "stress.db")

from iglegais import LocalMemoryGraph

fails = []


def check(name, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {name}" + (f"  -- {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def fresh(tag):
    """isolated db per scenario so tests never bleed into each other."""
    os.environ["IGLEGAIS_DB"] = os.path.join(WORKDIR, f"{tag}.db")
    g = LocalMemoryGraph()
    g.setup()
    return g


# 1. CYCLE: A causes B, B causes A. root_cause must terminate, not hang.
print("1. cycle termination (A<->B causal loop)")
g = fresh("cycle")
a = g.add("service a fell over")
b = g.add("service b fell over", causes=[a])
# manually close the loop: a caused_by b
g.conn.execute("INSERT OR IGNORE INTO edges(src,dst,rel) VALUES(?,?,?)", (a, b, "CAUSED_BY"))
g.conn.commit()
t0 = time.time()
chain = g.root_cause("service a fell over", max_depth=50)
elapsed = time.time() - t0
check("terminates under 2s", elapsed < 2.0, f"took {elapsed:.2f}s")
check("chain is finite and small", len(chain) <= 3, f"len={len(chain)}")

# 2. SELF LOOP: memory caused_by itself.
print("2. self loop (node caused_by itself)")
g = fresh("selfloop")
s = g.add("the thing broke")
g.conn.execute("INSERT OR IGNORE INTO edges(src,dst,rel) VALUES(?,?,?)", (s, s, "CAUSED_BY"))
g.conn.commit()
t0 = time.time()
chain = g.root_cause("the thing broke", max_depth=50)
check("self loop does not hang", time.time() - t0 < 2.0)
check("chain length 1", len(chain) == 1, f"len={len(chain)}")

# 3. DEEP CHAIN: 15 hops, walk all the way to the root with a big max_depth.
print("3. deep causal chain (15 hops)")
g = fresh("deep")
prev = g.add("root cause: a bad config value was committed")
labels = [prev]
for i in range(1, 15):
    prev = g.add(f"consequence step {i} in the failure cascade", causes=[prev])
    labels.append(prev)
symptom = g.add("the final user facing outage everyone noticed", causes=[prev])
chain = g.root_cause("what caused the final user facing outage?", max_depth=30)
check("reaches the true root", any("bad config value" in c for c in chain),
      f"chain tail={chain[-1:] }")
check("chain spans the depth", len(chain) >= 15, f"len={len(chain)}")

# 4. MAX_DEPTH is respected (don't over-walk).
print("4. max_depth cap is honored")
chain_capped = g.root_cause("what caused the final user facing outage?", max_depth=3)
check("stops at the cap", len(chain_capped) <= 4, f"len={len(chain_capped)}")

# 5. CROSS-INCIDENT DISCRIMINATION under heavy noise.
print("5. discrimination: 6 incidents + 120 noise memories, right root each time")
g = fresh("discriminate")
incidents = {
    "auth": ["migrated auth to a new jwt library", "users got logged out randomly", "support tickets about logouts spiked"],
    "cache": ["enabled an aggressive caching layer", "the dashboard showed stale numbers", "a customer reported wrong totals"],
    "disk": ["a log file grew without rotation", "the disk filled up on the db host", "writes started failing at midnight"],
    "deploy": ["a race condition slipped into the deploy script", "two workers clobbered the config file", "the service failed to boot after deploy"],
    "ratelimit": ["lowered the api rate limit by mistake", "third party calls began getting throttled", "checkout latency doubled"],
    "memleak": ["the image resizer leaked memory per request", "the box ran out of memory", "photo uploads started timing out"],
}
roots = {}
for key, chain in incidents.items():
    rid = g.add(chain[0])
    roots[key] = chain[0]
    prev = rid
    for step in chain[1:]:
        prev = g.add(step, causes=[prev])
# heavy noise
for i in range(120):
    g.add(f"routine log line number {i}: nothing interesting happened here")
symptoms = {
    "auth": "why were users getting logged out?",
    "cache": "why was the dashboard showing stale numbers?",
    "disk": "why did writes start failing at midnight?",
    "deploy": "why did the service fail to boot after deploy?",
    "ratelimit": "why did checkout latency double?",
    "memleak": "why did photo uploads start timing out?",
}
correct = 0
for key, q in symptoms.items():
    chain = g.root_cause(q, max_depth=8)
    got_root = chain[-1] if chain else ""
    ok = got_root == roots[key]
    correct += ok
    check(f"  {key}: root correct", ok, f"got '{got_root[:40]}' want '{roots[key][:40]}'")
check("all 6 incidents kept straight under noise", correct == 6, f"{correct}/6")

# 6. PERSISTENCE across reopen (close the handle, open a new engine, same file).
print("6. persistence across reopen")
os.environ["IGLEGAIS_DB"] = os.path.join(WORKDIR, "persist.db")
g1 = LocalMemoryGraph(); g1.setup()
p_root = g1.add("the certificate expired")
g1.add("tls handshakes started failing", causes=[p_root])
g1.conn.close()
g2 = LocalMemoryGraph()  # brand new engine, same file
chain = g2.root_cause("why did tls handshakes fail?", max_depth=5)
check("data survived reopen", any("certificate expired" in c for c in chain), f"chain={chain}")

# 7. EMPTY DB behaves.
print("7. empty database")
g = fresh("empty")
r = g.recall("anything at all")
check("recall on empty returns empty closest", r["closest_memory"] == [])
check("root_cause on empty returns []", g.root_cause("anything") == [])

# 8. NO-EDGE memory -> root_cause returns just itself.
print("8. single memory, no edges")
g = fresh("single")
g.add("a lonely fact with no causes")
chain = g.root_cause("tell me about the lonely fact")
check("chain is exactly the one memory", len(chain) == 1, f"len={len(chain)}")

# 9. UNICODE + very long content.
print("9. unicode and long content")
g = fresh("unicode")
g.add("the deploy broke because of an emoji in the config \U0001f4a5❤️")
long_root = g.add("root: " + ("x" * 20000))
g.add("downstream effect of the huge memory", causes=[long_root])
r = g.recall("emoji in the config")
check("unicode memory recalled", any("emoji" in c for c in r["closest_memory"]))
chain = g.root_cause("what was the downstream effect about?", max_depth=5)
check("20k char memory handled without crash", len(chain) >= 1)

# 10. SCALE: 400 memories, correct top-1 and acceptable latency.
print("10. scale: 400 memories, needle in haystack")
g = fresh("scale")
needle_root = g.add("the quarterly billing job double charged enterprise customers")
g.add("finance flagged duplicate invoices", causes=[needle_root])
for i in range(400):
    g.add(f"unrelated background event {i} about server metrics and cpu usage")
t0 = time.time()
chain = g.root_cause("why were enterprise customers double charged?", max_depth=5)
q_elapsed = time.time() - t0
check("finds the needle root among 400", any("double charged" in c for c in chain), f"chain={chain[-1:]}")
check("query under 3s at 400 rows", q_elapsed < 3.0, f"took {q_elapsed:.2f}s")

print()
if fails:
    print(f"FAILED ({len(fails)}): " + ", ".join(fails))
    raise SystemExit(1)
print("ALL BRUTAL TESTS PASSED")
