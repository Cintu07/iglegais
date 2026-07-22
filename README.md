<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/icon-dark.svg">
    <img src="assets/icon.svg" alt="iglegais" width="110">
  </picture>
</p>

# iglegais

memory that remembers why, not just what.

most memory tools keep your stuff as a flat pile of vectors. you ask something, they hand back the most similar chunk of text and call it a day. they cannot tell you why something happened, or how it changed over time.

iglegais stores each memory as a node with a vector *and* typed edges (`caused_by`, `contradicts`, `follows`). so recall does two things a flat store simply cannot:

1. vector search to find the memory you actually mean
2. walk the graph to hand you its cause, its contradictions, and how it evolved

## the demo

```
Q: why did the pipeline go down?

closest memory:
   "ops got paged at 2am: the zorbex-9 pipeline went completely down."

caused by:
   "the zorbex-9 module leaked memory and crashed the data pipeline."

later fixed by:
   "patched the zorbex-9 memory leak and the pipeline recovered."
```

a flat store gives you the first line and shrugs. the graph is what finds the root cause.

## real world test

two totally separate incidents (an auth outage and a caching bug) jumbled into one graph. the hard part is telling them apart and blaming the right thing:

```
Q: why were users getting logged out?
   root cause:  migrated the auth service to a new jwt library     (correct)

Q: why was the dashboard showing old numbers?
   root cause:  enabled a new caching layer                        (correct)

both passed. it kept the incidents straight.
```

## runs on your machine, costs nothing

everything lives in a single local file. local embeddings, no server to run, no
cloud, no bill. your memories never leave the machine.

## use it

```bash
pip install iglegais
```

that's it. no database to install, nothing to start. add it to your assistant:

```bash
claude mcp add iglegais -- iglegais
```

your assistant now has three tools: `remember`, `recall`, `why`. it stores
plain text, and it can walk a chain of causes when you ask why something
happened.

```text
you: remember: the deploy failed because of a race in migrations
you: why did the deploy fail?
```

memories are kept in `~/.iglegais/memory.db` (override with `IGLEGAIS_DB`).

### library use

same three calls:

```python
from iglegais import MemoryGraph

mg = MemoryGraph()
mg.setup()
mg.add("the deploy had a race condition")                 # or explicit edges
mg.recall("why did the service fail to boot?")            # cause + contradictions
mg.root_cause("why did the service fail to boot?")        # full chain to the root
```

### automatic edge inference (optional)

`remember(content)` can infer `caused_by` / `contradicts` / `follows` edges from
plain text using a hosted model. set a free `CEREBRAS_API_KEY` in the
environment or `~/.iglegais/.env` to turn it on. without a key, use `add()` with
explicit edges (shown above); everything else works the same.

### bigger datasets (optional)

for very large memory sets you can point iglegais at a graph+vector server
instead of the local file: set `IGLEGAIS_BACKEND=helix` (and `HELIX_URL` if not
`localhost:6969`). the local file is the default and is plenty for personal use.

### run the tests

```bash
python verify_local.py   # local backend, no server: asserts the root cause is found
python stress_test.py    # brutal suite: cycles, deep chains, discrimination under noise, scale
```

the stress suite tries to break the engine: causal loops and self loops (must
not hang), a 15 hop chain, six separate incidents jumbled with 120 noise
memories (must keep every root straight), persistence across reopen, unicode
and 20k char memories, and a needle in a 400 memory haystack.

### benchmark: root-cause retrieval

```bash
python benchmark.py
```

this measures the one thing this is built for: given a symptom question, return
the root cause, which sits several hops away and is worded nothing like the
symptom. same corpus, three systems:

```
corpus: 8 incidents, 224 total memories

  A. flat vector top-1   root-cause accuracy:  0%
  B. flat vector top-3   root-cause recall  :  0%
  C. iglegais root_cause accuracy           : 100%    (median 11 ms/query)
```

similarity search lands on the symptom or a distractor and misses the cause.
walking the causal graph is what recovers the actual root. this is not a general
memory database benchmark, it is the causal slice, run it yourself.

## how it works

- `add(content, ...)` embeds the text and stores a memory node with optional
  `caused_by` / `contradicts` / `follows` edges to earlier memories.
- `recall(query)` vector searches to the closest memory, then walks the
  edges to give you the reasoning around it.
- `root_cause(query)` keeps walking `caused_by` hops until it hits the root.

a few hundred lines of python: memories are rows, edges are rows, vector search
is a dot product over normalized embeddings. small on purpose.

## where it goes next

- per user memory spaces
- dedup on ingest
- flag stale memories when a newer one contradicts them
- a visual graph of your memory

---

built by [@Cintu07](https://github.com/Cintu07).
