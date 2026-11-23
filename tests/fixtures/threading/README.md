# Thread-assignment labeled sets

Owner-labeled, from real stored items (headlines only, no excerpts). Used by
`tests/process/test_thread_tuning.py` (DESIGN §6.5).

## Labeling rubric (owner, 2026-11-22)

Ask: *would I want this item as the next update in this thread, read right after
its earlier headlines?*

1. **Same event or its direct consequences** → yes. Fallout counts only if the event caused it.
2. **Analysis or opinion about that same event** → yes.
3. **Same people, company or event, and its implications** → yes. A thread is a wide shot of
   them, not one narrow development.
4. **An ongoing war is one thread**: strikes, counter-strikes and other developments of
   the same war belong together.
5. **A product line is one thread** (Gemini 4 models, ChatGPT products).
6. **A different event that only shares a theme** → no. Example: a general piece on nuclear
   arms policy vs. the Trump–Xi–Putin summit's takeaways.
7. Judge against the headlines shown, not what the thread became later.
8. Unsure → no: a wrong merge muddles a thread; a missed one only leaves the item alone.

Rules 3 and 4 were widened after the pairs below were labeled (see DESIGN §6.5).

## `pairs.json`

50 pairs, `label: true` = the two belong in the same thread; same topic in every
pair. `cosine` is the bge-small-en-v1.5 similarity of title + excerpt, recorded at
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
