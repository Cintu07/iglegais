"""honest benchmark: causal root-cause retrieval.

this does NOT claim to be a general memory database benchmark. it measures one
specific thing iglegais is built for and that flat vector retrieval is not:
given a SYMPTOM question, return the ROOT CAUSE, which is usually several hops
away and phrased nothing like the symptom.

setup: many independent incidents. each is a causal chain
  root cause  ->  intermediate  ->  ...  ->  symptom
plus a pile of unrelated distractor memories. we ask a symptom question and
score whether the returned root cause is the TRUE root of that incident.

we compare three systems on the same data:
  A. flat vector top-1     (what a plain vector store returns)
  B. flat vector top-3     (generous: root anywhere in the top 3 counts)
  C. iglegais root_cause   (vector-search to the symptom, then walk causes)

reproducible: python benchmark.py
"""
import os
import random
import tempfile
import time

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ["IGLEGAIS_DB"] = os.path.join(tempfile.mkdtemp(), "bench.db")

import numpy as np

from iglegais import LocalMemoryGraph
from iglegais.embedding import embed

random.seed(7)

# ---- generate a realistic-ish incident corpus -------------------------------
# each incident: a root cause phrased very differently from the symptom, a chain
# of consequences, and a natural-language "why" question about the symptom.
INCIDENTS = [
    dict(root="a database index was dropped during a schema migration",
         chain=["queries began doing full table scans",
                "api p99 latency climbed past 8 seconds"],
         symptom="why did the api get so slow?"),
    dict(root="an expired oauth client secret was never rotated",
         chain=["the background sync could not authenticate",
                "new orders stopped appearing in the warehouse"],
         symptom="why are new orders missing from the warehouse?"),
    dict(root="a feature flag defaulted to on for all tenants",
         chain=["an unfinished billing path executed in production",
                "some customers were charged twice"],
         symptom="why did customers get double charged?"),
    dict(root="the cdn cache ttl was set to a year by a typo",
         chain=["users kept receiving an old broken javascript bundle",
                "the signup button stopped working for everyone"],
         symptom="why is the signup button broken?"),
    dict(root="a cron job wrote logs without any rotation",
         chain=["the disk on the primary node filled to 100 percent",
                "the database went read only at 3am"],
         symptom="why did the database become read only overnight?"),
    dict(root="a shared thread pool was sized to two by mistake",
         chain=["requests queued up behind slow downstream calls",
                "the checkout page began timing out under load"],
         symptom="why does checkout time out when traffic is high?"),
    dict(root="timezone handling assumed the server was always utc",
         chain=["scheduled reports generated with a seven hour offset",
                "the morning dashboard showed yesterday's numbers"],
         symptom="why is the dashboard showing stale numbers in the morning?"),
    dict(root="a retry loop had no backoff or jitter",
         chain=["a brief blip turned into a thundering herd",
                "the payment provider rate limited the whole account"],
         symptom="why did the payment provider start rejecting our calls?"),
]

DISTRACTORS = [
    "the design team shipped a new marketing landing page",
    "we upgraded the ci runners to a faster instance type",
    "someone renamed a slack channel about lunch orders",
    "the onboarding email copy was reworded for clarity",
    "a dependency bumped its patch version with no code change",
    "the office wifi was rebooted on tuesday afternoon",
    "we added a dark mode toggle to the settings page",
    "the quarterly all hands was moved to a different room",
]


def build(mg, n_distractors_per_incident=25):
    truth = []  # (symptom_question, true_root_text)
    for inc in INCIDENTS:
        rid = mg.add(inc["root"])
        prev = rid
        for step in inc["chain"]:
            prev = mg.add(step, causes=[prev])
        truth.append((inc["symptom"], inc["root"]))
        # bury each incident under fresh distractor noise
        for i in range(n_distractors_per_incident):
            d = random.choice(DISTRACTORS)
            mg.add(f"{d} (note {random.randint(0, 99999)})")
    return truth


def flat_vector_topk(mg, query, k):
    """what a plain vector store does: return the k most similar memories."""
    return [content for _, _, content in mg._search(query, k)]


def main():
    mg = LocalMemoryGraph()
    mg.setup()
    t0 = time.time()
    truth = build(mg)
    n_mem = mg.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    build_s = time.time() - t0

    top1_hits = top3_hits = igle_hits = 0
    igle_latency = []

    for symptom, true_root in truth:
        top3 = flat_vector_topk(mg, symptom, 3)
        if top3 and top3[0] == true_root:
            top1_hits += 1
        if true_root in top3:
            top3_hits += 1

        t = time.time()
        chain = mg.root_cause(symptom, max_depth=8)
        igle_latency.append(time.time() - t)
        got_root = chain[-1] if chain else ""
        if got_root == true_root:
            igle_hits += 1

    n = len(truth)
    print(f"corpus: {n} incidents, {n_mem} total memories, built in {build_s:.1f}s")
    print(f"queries: {n} symptom questions, each asking for a root cause\n")
    print(f"  A. flat vector top-1   root-cause accuracy: {top1_hits}/{n}  ({100*top1_hits/n:.0f}%)")
    print(f"  B. flat vector top-3   root-cause recall  : {top3_hits}/{n}  ({100*top3_hits/n:.0f}%)")
    print(f"  C. iglegais root_cause accuracy           : {igle_hits}/{n}  ({100*igle_hits/n:.0f}%)")
    print(f"\n  iglegais median query latency: {1000*np.median(igle_latency):.0f} ms")
    print("\ninterpretation: the root cause is worded nothing like the symptom, so")
    print("similarity search lands on the symptom or a distractor and misses the")
    print("cause. walking the causal graph is what recovers the actual root.")


# ---- part 2: temporal current-truth retrieval ------------------------------
UPDATED_FACTS = [
    ("the primary database is postgres", "the primary database is now mysql"),
    ("our ci runs on jenkins", "our ci runs on github actions now"),
    ("the team is based in berlin", "the team relocated to lisbon"),
    ("we deploy once a week", "we deploy continuously now"),
    ("auth uses session cookies", "auth now uses signed jwt tokens"),
    ("the app is written in flask", "the app was rewritten in fastapi"),
    ("we bill monthly", "we switched to usage based billing"),
    ("logs go to a local file", "logs now ship to a central service"),
]
TEMPORAL_QUERIES = [
    "what database do we use?", "what runs our ci?", "where is the team?",
    "how often do we deploy?", "how does auth work?", "what framework is the app?",
    "how do we bill?", "where do logs go?",
]


def temporal_benchmark():
    os.environ["IGLEGAIS_DB"] = os.path.join(tempfile.mkdtemp(), "bench_t.db")
    mg = LocalMemoryGraph()
    mg.setup()
    ts = 1000
    for old, new in UPDATED_FACTS:
        o = mg.add(old)
        mg.conn.execute("UPDATE memories SET ts=? WHERE id=?", (ts, o))
        n = mg.add(new, contradicts=[o])
        mg.conn.execute("UPDATE memories SET ts=? WHERE id=?", (ts + 1, n))
        ts += 10
    mg.conn.commit()

    flat_current = igle_current = 0
    for (old, new), q in zip(UPDATED_FACTS, TEMPORAL_QUERIES):
        flat_top1 = mg._search(q, 1)[0][2]
        if flat_top1 == new:
            flat_current += 1
        ans = mg.what_is_true(q)["answer"] or ""
        if ans == new:
            igle_current += 1

    n = len(UPDATED_FACTS)
    print("\n" + "=" * 62)
    print("PART 2: temporal current-truth retrieval")
    print("=" * 62)
    print(f"corpus: {n} facts, each later contradicted by an updated fact\n")
    print(f"  flat vector top-1  current-truth accuracy: {flat_current}/{n}  ({100*flat_current/n:.0f}%)")
    print(f"  iglegais what_is_true accuracy           : {igle_current}/{n}  ({100*igle_current/n:.0f}%)")
    print("\ninterpretation: the stale and updated facts are both similar to the")
    print("query, so similarity search cannot tell which one is still true. the")
    print("contradiction edge plus timestamps is what returns the current answer.")


if __name__ == "__main__":
    main()
    temporal_benchmark()
