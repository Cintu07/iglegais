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

```bash
# 1. run a local graph+vector instance on localhost:6969
# 2. then:
python mg.py        # ingest a causal story, recall the cause
python verify.py    # asserts the traversal returns the root cause
python realtest.py  # two incidents, correct cause for each
```

## how it works

- `add(content, causes=[], contradicts=[], follows=id)` embeds the text, adds a memory node, and links the edges.
- `recall(query)` vector searches to the closest memory, then walks `caused_by` and `contradicts` to give you the reasoning around it.

about 120 lines of python over a graph+vector engine. small on purpose. the engine does the heavy lifting, iglegais is the brain wiring on top.

## where it goes next

- infer the edges automatically from raw text instead of passing them by hand
- trace root cause multiple hops deep
- flag stale memories when a newer one contradicts them
- expose it as a tool so an ai assistant can use it as long term memory

---

built by [@Cintu07](https://github.com/Cintu07).
