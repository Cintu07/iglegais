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

a local graph+vector database, local embeddings, no cloud, no api keys, no bill. your memories never leave the machine.

## use it

three steps.

```bash
# 1. run a local graph+vector instance on localhost:6969 (persistent mode)

# 2. get a free llm key for edge inference (cerebras free tier works) and
#    drop it in a .env file next to where you run things:
#    CEREBRAS_API_KEY=csk-...

# 3. install and wire it into your assistant:
pip install iglegais
claude mcp add iglegais -- iglegais
```

your assistant now has three tools: `remember`, `recall`, `why`. it stores
plain text, the causal links get inferred automatically, and it can walk
a chain of causes when you ask why something happened.

library use, same three calls:

```python
from iglegais import MemoryGraph

mg = MemoryGraph()
mg.setup()
mg.remember("the deploy script had a race condition")   # edges inferred
mg.recall("why did the service fail to boot?")            # cause + contradictions
mg.root_cause("why did the service fail to boot?")        # full chain to the root
```

or clone the repo and run the tests against your local instance:

```bash
python verify.py    # asserts the traversal returns the root cause
python realtest.py  # two mixed incidents, correct cause for each
python multihop.py  # walks a 3 level chain to the root
```

## how it works

- `remember(content)` embeds the text, adds a memory node, and lets an llm
  infer `caused_by` / `contradicts` / `follows` edges to earlier memories.
- `recall(query)` vector searches to the closest memory, then walks the
  edges to give you the reasoning around it.
- `root_cause(query)` keeps walking `caused_by` hops until it hits the root.

a few hundred lines of python over a graph+vector engine. small on purpose.
the engine does the heavy lifting, iglegais is the brain wiring on top.

## where it goes next

- per user memory spaces
- dedup on ingest
- flag stale memories when a newer one contradicts them
- a visual graph of your memory

---

built by [@Cintu07](https://github.com/Cintu07).
