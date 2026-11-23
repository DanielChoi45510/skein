# Thread-assignment labeled set

`pairs.json`: 50 pairs of real stored items (headlines only, no excerpts),
labeled by the owner on 2026-11-22: `label: true` means the two belong in the
same thread. Same topic in every pair.

- `cosine`: bge-small-en-v1.5 similarity of the two items' title + excerpt,
  recorded at labeling time, so tests need no model. The entity boost is
  recomputed from the titles.
- `batch` 1: 30 pairs sampled evenly over 0.45–0.95; `batch` 2: 20 more over
  0.65–0.85, where the decision is made.

Rebuild or extend: `python -m pipeline.threadpairs pairs --state DIR [--range LO HI]
--exclude tests/fixtures/threading/pairs.json --out new.json`, label it, merge.
Evaluate: `python -m pipeline.threadpairs evaluate --pairs tests/fixtures/threading/pairs.json`.
Used by `tests/process/test_thread_tuning.py` (DESIGN §6.5).
