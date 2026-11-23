# Thread-assignment labeled sets

Owner-labeled, from real stored items (headlines only, no excerpts). Used by
`tests/process/test_thread_tuning.py` (DESIGN §6.5).

## Labeling rubric (owner, 2026-11-22): a thread is one subject

A thread is **one subject the news keeps coming back to**, with its developments,
consequences and commentary:

- a company or organization (Nvidia, Anthropic, OpenAI);
- a product line (Gemini, ChatGPT);
- a war or conflict (the Ukraine war, the Iran war);
- a specific event and its aftermath (the Trump–Xi–Putin summit, COP31, the House
  majority result, the lame-duck session);
- in health topics: one health question or public-health story (the measles comeback).

Topics (AI news, US politics, World news …) are the umbrellas above threads.

1. **Same subject → same**, even from a different angle: Anthropic's IPO and its
   safety stance; Nvidia's scandal, chips and export policy; the Iran war's fallout
   and its tanker strikes.
2. **Implications and consequences of an event belong to it** (oil pledges made at
   the summit).
3. **Group by what the story is about, not who is mentioned**: a name that's
   everywhere in a topic (Trump in US politics, "AI" in AI news) doesn't make two
   stories one subject.
4. **Different subjects that only share a theme → different** (general nuclear-arms
   policy vs. the summit; AI-at-work essays about different companies).
5. An item about two subjects goes with the one it's mainly about.
6. Judge against the headlines shown, not what the thread became later.
7. **Unsure → different**: a wrong merge muddles a thread; a missed one only leaves
   the item alone.

The first labels used a narrower grain (one storyline); 13 pairs were relabeled
"same" under this rubric (`relabeled` field). The joins were labeled in between
and fit this rubric unchanged.

## `pairs.json`

50 pairs (31 same, 19 different), `label: true` = the two belong in the same
thread; same topic in every pair. `cosine` is the bge-small-en-v1.5 similarity of title + excerpt, recorded at
labeling time, so tests need no model; the entity boost is recomputed from the
titles. `batch` 1: 30 pairs sampled evenly over 0.45–0.95; `batch` 2: 20 more over
0.65–0.85.

## `joins.json`

20 real joins from a full run (2026-11-22): an item and the thread's headlines
when it joined. `label: true` = it belongs. `score` is the recorded
`thread_score` (cosine with the centroid + entity boost). `group` `multi`: the
thread already had ≥ 2 items (16, scores 0.80–0.88); `single`: one item (4,
0.80–0.84). Only joins above the cut in force can be sampled, so this set can
show a cut is too low, never too high.

## Tools

```sh
python -m pipeline.threadpairs pairs --state DIR [--range LO HI] --exclude tests/fixtures/threading/pairs.json --out new.json
python -m pipeline.threadpairs evaluate --pairs tests/fixtures/threading/pairs.json
python -m pipeline.threadpairs joins --state DIR --out joins.json      # after a run
python -m pipeline.threadpairs evaluate-joins --joins tests/fixtures/threading/joins.json
```
