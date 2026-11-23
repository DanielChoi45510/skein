# Skein — Design

Status: draft v0.1 (2026-11-21), written from the planning interview. Sections marked **[open]** still need a decision.

---

## 1. Purpose

A replacement for social-media scrolling: one calm, finite feed of things the owner actually wants to know about. It is tailored by config, grouped into evolving story threads so context builds up over days, and readable on phone and laptop.

**Goals**

- Catch up in one sitting (normally once a day, sometimes 2–3 times).
- Understand *how a story evolved*, not just today's headline.
- Facts and numbers over takes, hype, doom and engagement bait.
- Make it easy to add, remove and trial sources and topics; interests will change.
- Cost nothing to run.
- Eventually be forkable: someone else edits `config/` and runs their own.

**Non-goals:** see "Not in scope" in `CLAUDE.md`.

## 2. Owner reading profile (public-safe)

- Reads the **full article** at the source; doesn't want AI summaries in place of articles. Exception: research studies, where a structured summary of the abstract is wanted (§8.2).
- Has an NYT student subscription. No other paywalled subscriptions.
- Opinion pieces are welcome if they're **labeled** and drawn from **across the political spectrum**.
- Low tolerance for: hype, memes, doom posting, listicles (except shopping research), influencer content, emotionally charged extreme takes, obvious advice dressed up as news.
- Personal details (current gear, health context, job-search profile) live only in the private profile (§10.3).

## 3. Core concepts

```
Source ──produces──▶ Item ──belongs to (0..1)──▶ Thread ──belongs to──▶ Topic
```

| Concept | Meaning |
|---|---|
| **Source** | A feed or endpoint: RSS/Atom, subreddit, study database query, job board. Defined in `config/sources.yaml`. |
| **Item** | One article, post, study or job listing. Holds metadata and a link only, never full text. |
| **Topic** | One of the owner's interests, described in plain English (`config/topics.yaml`). The description drives relevance matching. |
| **Thread** | An ongoing story or question inside a topic. Items attach to threads over time. |
| **Group** | UI grouping of topics (AI, Tech, Games, Health, News, Money & Jobs, Reading). |

### 3.1 Data model (sketch)

```ts
// Matches config/sources.yaml; enforced by pipeline/config/schema.py.
type Source = {
  id: string;
  type: "rss" | "reddit"                    // fetched since Phase 1
      | "github_list" | "nyt_books" | "fred"; // Phase 4 fetchers; must stay disabled until then
  name?: string;                            // display name; else the feed's own title, else the id
  url?: string;                             // rss only (Phase 4 types keep settings in options)
  subreddit?: string;                       // reddit only
  topics: string[];                         // which topics it may feed
  status: "active" | "trial" | "disabled";
  weight: number;                           // 0.5–1.5, manual trust knob (default 1.0)
  lean?: "left" | "lean_left" | "center" | "lean_right" | "right" | null; // AllSides; only with kind reporting/analysis/opinion
  kind?: "reporting" | "analysis" | "opinion" | "study" | "listing" | "guide"; // default content-kind hint
  paywall: "none" | "partial" | "full";     // default none; partial/full show a 🔒 badge
  verified: boolean;                        // returned a valid feed in a real run (default false)
  excerpt: boolean;                         // default true; false drops the feed's description (boilerplate feeds)
  relevance?: { threshold: number } | { skip: true };  // §6.4
  title_exclude?: string[];                 // regexes (case-insensitive): matching titles are dropped / hidden (§6.2)
  title_strip?: string[];                   // regexes (case-insensitive): matching text is removed from titles (§6.2)
  options?: Record<string, unknown>;        // e.g. reddit min_score; region (§8.4); Phase 4 type settings
};

// Stored as NDJSON in items/YYYY-MM-DD.ndjson (by first_seen_at); see pipeline/models.py.
type Item = {
  id: string;                 // first 16 hex chars of sha256(canonical URL)
  source_id: string; url: string; canonical_url: string;   // url = original link, used for linking out
  title: string; excerpt?: string;          // feed-provided, plain text, ≤300 chars
  published_at: string;       // UTC; missing or future dates → first_seen_at
  first_seen_at: string;      // run that first stored it; never changes
  also_covered_by: string[];  // other sources with the same story (§6.3), a ranking signal
  duplicate_of?: string;      // set with hidden_reason "duplicate"
  topic_id?: string; thread_id?: string;
  relevance?: number;         // 0–1 (§6.4); topic_id is the best-scoring topic
  thread_score?: number;      // similarity to the thread when attached (rescue, §6.5)
  // importance (§6.6) depends on the current time: computed at export, never stored
  extra: Record<string, unknown>;           // small source metadata (e.g. Reddit score, flair)
  labels: {
    kind?: "reporting" | "analysis" | "opinion" | "study" | "listing" | "guide";
    credibility?: "beta_confirmed" | "reputable_leaker" | "unverified" | "fake";   // parked leaks topic (§16)
    evidence?: "strong" | "moderate" | "weak";                                     // studies
    region?: string;          // world news
    flags?: string[];         // e.g. "listicle", "spoiler_risk", "overclaim"
  };
  hidden_reason?: "duplicate";  // more reasons arrive with filters (§7); thresholds are applied at export, not stored
  study_card?: StudyCard;     // §8.2
};

// Stored in threads.json; see pipeline/models.py.
type Thread = {
  id: string; topic_id: string;
  kind: "story" | "tracker" | "question" | "fixed";   // from the topic's mode ("patch" is parked, §16)
  title: string;              // LLM-named, or keyword fallback; config title for tracker/fixed threads
  state: "pending" | "active" | "cooling" | "dormant" | "archived";
  created_at: string; last_item_at: string;           // last_item_at: newest item's published_at
  // centroid: stored separately (centroids.npy, §10.1), only while the thread can be matched
  item_ids: string[];         // in attach order
  primer?: { text: string; sources: string[]; generated_at: string };   // §8.5
  region?: string;
  pinned?: boolean; muted?: boolean;          // owner overrides
};
```

## 4. Topic modes

Each topic in `topics.yaml` has a `mode`:

| Mode | Behavior | Used by |
|---|---|---|
| `threaded` | Items cluster into story threads automatically (§6.5). Threads go through the lifecycle in §5. | AI news, US politics, World news, Job-market news |
| `flat` | No threads. A ranked list with a daily or weekly cap. | AI in practice, Everyday upgrades, Job-search guides |
| `tracker` | Fixed, never-ending threads, one per product category. Items are compared against the owner's private gear list. | Tech trackers |
| `question` | Threads are research questions ("training volume for hypertrophy"). They collect studies for months and go dormant slowly. | Health topics |
| `fixed` | Predefined threads only (no automatic creation). | Markets (sectors + economy-wide) |
| `listings` | Job listings matched to the private profile, with a weekly target count. | Jobs: listings |
| `reading_list` | Slow lane, a few picks a month. | Books |

## 5. Thread lifecycle

```
pending ──(2+ items or high importance)──▶ active ──(no items N days)──▶ cooling ──▶ dormant ──▶ archived
                                              ▲                                        │
                                              └──────── new matching item ◀────────────┘
```

- **pending:** a new thread with one item. Shown inline as a single item and only promoted to a thread when a second item arrives within 72 h, or when the first item's importance is very high: in practice, at least 2 other sources carried it (`also_covered_by`), since importance itself depends on the time of export. This prevents a flood of one-item threads. After 72 h a pending thread can no longer be matched (its centroid is dropped); its item stays a single item.
- **cooling:** sinks in the topic list.
- **dormant:** grayed out and collapsed at the bottom of the topic.
- **archived:** hidden; searchable. Its centroid is dropped, so it is never matched again (§6.5).
- A cooling or dormant thread **revives** (back to active) when a new item matches it, keeping its full history. Archived threads don't revive: a new item starts a new thread. When an archived story resurfaces, the owner joins the new thread to the old one with the **merge** override (Phase 2b, below); the pipeline never does this on its own.
- Timings are per topic, counted from the thread's last item: `cooling_after_days`, `dormant_after_days`, `archive_after_days` (topic override, else `defaults`). The validator requires cooling < dormant < archive, and rejects these keys on tracker and fixed topics. Defaults: cooling 3 days (health questions 30); dormant: politics 10, world and jobs 14, AI 21, health 120. Tracker and fixed threads never cool, go dormant or archive.

Code: `pipeline/process/lifecycle.py`, run every pipeline run, so states follow the clock even without new items. Threads whose topic left the config or stopped being threaded, and predefined threads removed from the config, are archived. Pending and archived threads none of whose items are still loaded (the 30-day item window) are deleted from `threads.json`.

**Titles** (until Phase 3 names threads with the LLM): a promoted thread is titled with up to 4 words its headlines share, as "A · B · C". Words used by more headlines come first, named entities win ties, and the order and spelling follow the newest headline, e.g. "GPT-6.2 · Astra · Sol" or "Trump · Xi · Putin · Historic". With fewer than two shared words, the newest headline is the title. Pending threads use their item's headline; tracker and fixed threads keep their config title. Titles are recomputed whenever items attach.

**Owner overrides** (Phase 2b; stored by the Worker, applied at the start of each pipeline run): rename, pin, mute, merge two threads, split items out to a new thread, move an item to another thread.

## 6. Pipeline

Runs hourly in GitHub Actions, plus on demand via the refresh button (§9.2). Each run is idempotent.

```
fetch → normalize → dedupe → embed → relevance → classify/filter → assign thread → rank & cap → enrich (LLM) → export → deploy
```

### 6.1 Fetch
- Conditional GET (ETag / Last-Modified); unchanged feeds cost nothing.
- Per-host rate limits, timeouts, retries with backoff, descriptive User-Agent.
- Reddit via its public RSS/JSON endpoints, which may be rate-limited or blocked from cloud runners. A source failure must not fail the run; it's recorded in source health (§9.4).
- Source types since Phase 1: `rss`, `reddit`. `rss` also covers Google News search feeds (used for Reuters, which has no official feed); their items have headlines only and link through news.google.com.
- Phase 4 adds `github_list` (SimplifyJobs JSON listings), `nyt_books` (NYT Books API) and `fred` (FRED series observations). Until their fetchers exist, sources of these types must be `status: disabled` (validator rule). Later still: companies' public Greenhouse / Lever / Ashby job boards (§8.7).
- `options.region` on a source pre-tags its items for a topic's region facet (§8.4). It must be one of the `regions` of a topic the source feeds.

### 6.2 Normalize
Canonicalize URLs (strip tracking params), parse dates to UTC, trim the excerpt to ≤300 chars, and drop items older than the topic's lookback window.
- **Titles** are cleaned: inline formatting tags (`<i>`, `<em>`, `<b>`, `<a>`, `<span>` …) are removed and entities decoded, because some feeds double-encode markup. Other angle-bracket text stays: a literal "<canvas>" in a headline is text. The export cleans titles again, so items stored before this rule display the same.
- **`title_exclude`** (per source, `sources.yaml`): entries whose cleaned title matches any pattern are dropped. Stored items are checked again at export and before threading, so a new pattern also hides what the source already delivered. An item stays if another source that carried it doesn't exclude it (as with thresholds, §6.4). First use: the Reuters markets search feed returns stock-quote pages ("Nutrien Ltd (NTR.TO) | Stock Price & Latest News - Reuters"): 94 of its first 96 items (2026-11-22).
- **`title_strip`** (per source): matching text is then removed from the title, e.g. the " - Reuters" that Google News appends; the card already shows the source. It runs after `title_exclude`, so exclude patterns see the title as sent. It never strips a title to nothing, and the export applies it again for titles stored before.

### 6.3 Dedupe
1. Exact: canonical URL hash (tracking params like `utm_*`, `smid`, `fbclid` stripped; fragment dropped; params sorted). A second source adds itself to `also_covered_by`; a strictly higher-weight source takes the item over.
2. Near-duplicate: title-embedding cosine ≥ 0.92 within 48 h → keep the higher-weight source (ties: the item stored first), record the others as `also_covered_by` (used as a corroboration signal in ranking). The hidden one is kept with `duplicate_of`, so reruns recognize it by id.

### 6.4 Embed and relevance
- Small CPU embedding model: `BAAI/bge-small-en-v1.5` (optional `[embed]` extra), cached between runs with the Actions cache. Loaded only when a run has new items. Whether anchors get bge's query instruction is a constant (`USE_QUERY_INSTRUCTION`), chosen by calibration.
- Each topic's `description` + `include` examples are embedded as positive anchors, and its `exclude` examples as negative anchors. Items are embedded as title + excerpt.
- `relevance = pos − λ·max(0, neg − pos)` with `pos`/`neg` the max similarity to the positive/negative anchors, λ = 0.5, clipped to [0, 1]. An exclude only counts against items closer to it than to the topic: subtracting `λ·neg` outright dropped every item in topics with in-domain excludes (calibration, 2026-11-21). Items from sources mapped to several topics go to the best-scoring one (ties: first listed).
- Only the score is stored; thresholds are applied at export, so a threshold change takes effect on the next run for stored items too.
- Threshold precedence: source `relevance.threshold` → topic `relevance_threshold` → `defaults.relevance_threshold`. A single-topic source can set `relevance: {skip: true}`: its items are never hidden by a threshold but are still scored, so ranking uses real relevance.
- An item is shown if any source that carried it (its own or `also_covered_by`) would show it, so a story a skip source carried isn't hidden because another source's copy scored low.
- Calibrate with `python -m pipeline.calibrate --state DIR`: scores stored items (instruction off and on) and prints per-topic percentiles, counts kept at candidate thresholds, and sample titles.
- For job listings and gear trackers, the private profile adds an extra similarity term (§10.3).

### 6.5 Thread assignment (threaded / question / tracker / fixed)
Code: `pipeline/process/threads.py`. For each relevant item in a `threaded` or `question` topic (visible, within lookback, passing the relevance threshold), in (published_at, id) order:
1. Candidates: the topic's threads that can still be matched: active, cooling and dormant, plus pending threads less than 72 h old. Never archived (§5). Score = cosine(item, thread centroid) + entity boost: +0.02 per named entity shared with the thread's item titles, capped at +0.06. Entities are rough: tokens with digits (GPT-5), acronyms (NATO), mixed case (OpenAI) and capitalized non-first words, minus common title-case words and bracketed feed tags ("[AINews]").
2. Top score ≥ `T_high` (**0.82**) with a margin ≥ 0.05 over the second → attach.
3. Between `T_low` (**0.65**) and `T_high`, or ≥ `T_high` without the margin → the gray zone: ask the LLM to pick among the top 3 or "new thread" (Phase 3). If the LLM is unavailable, attach if the score reaches the cut, else new:
   - `fallback` (**0.68**) for a one-item (pending) thread;
   - `grown` (**0.80**) for a thread that already has 2+ items.

   Until Phase 3, these two cuts are what actually decide attach vs. new.
4. Otherwise → new `pending` thread.
5. Update the centroid as a recency-weighted average: `c ← normalize((1−α)c + αv)`, α = max(1/n, 0.25).

Mode-specific rules:
- `tracker` and `fixed`: assign every eligible item to the nearest predefined thread; never create new ones. Each thread's anchor is the embedding of its optional `description` in `topics.yaml`, else its title. A bare title is a weak anchor: with titles only, iPhone and AirPods items went to Wearables (2026-11-22).

**Per run** (`pipeline/process/thread_assign.py`, after relevance scoring):
- **Who gets assigned:** items in a threaded, question, tracker or fixed topic that are visible, within the topic's lookback, carried by an enabled source, not excluded by title, and not yet in a thread.
  - Items that pass the relevance threshold are assigned.
  - Items in the rescue band are tried only in the run that first stores them, so a near-miss isn't re-embedded every hour.
- **Backfill:** passing items with no thread (all stored items on the first Phase 2a run, or more after a threshold is lowered) are embedded again and assigned.
- **Order and deps:** items go in (published_at, id) order, so later items can join threads that earlier ones in the same run started. The model is loaded only when something needs a vector.
- **New threads:** a new pending thread's `created_at` is its item's `first_seen_at`, and its founding item gets `thread_score` 1.0. Tracker and fixed thread records are created when their first item arrives.
- **Wrap-up:** then the lifecycle runs (§5), threads that changed are retitled, and unused threads are pruned.

**Tuning** (2026-11-22). Labeled set: 50 owner-labeled pairs of real stored items in `tests/fixtures/threading/pairs.json` (18 same thread, 32 different; recorded bge cosines, so tests need no model). **Thread grain** (owner rubric, `tests/fixtures/threading/README.md`): a thread is **one subject** the news keeps coming back to, with its developments, consequences and commentary. That can be a company (Nvidia: scandal, chips and exports together), a product line (Gemini), a war (Ukraine), or an event and its aftermath (the Trump–Xi–Putin summit). Topics are the umbrellas above threads. Group by what a story is about, not who it mentions: Trump in US politics doesn't make two stories one subject. Different subjects that only share a theme stay apart. `python -m pipeline.threadpairs pairs` samples new pairs; `evaluate` grid-searches `fallback` and the boost, ranking by F0.5 because a wrong merge is worse than a missed one.
- **`fallback` 0.68** with the 0.02 boost, at the subject grain (31 same, 19 different): 28 of 31 joined, 3 of 19 merged (precision and recall 0.90). At the first, narrower grain the best cut was 0.80.
- `T_high` 0.82 sits above the best-scoring different pair (0.79); `T_low` 0.65 sits at or below the worst-scoring true pair (0.653).
- The margin can't be measured on pairs (one candidate each), so the 0.05 guess stays.
- Pairs stand in for item-vs-centroid scores: for a one-item pending thread they are the same. Joins to grown threads score higher, because a centroid is an average and so more generic.
- **Real joins** (`joins.json`, 20 joins from the first full run, cut 0.80): 18 of 20 belong. At 0.83 the two wrong joins go, but so do 8 of the 18 right ones.
- **Why grown threads need their own cut.** At 0.68 for every thread, a re-run of the first full run chained: an op-ed seeded a 78-item catch-all of US politics opinion (45% of the topic). Each loose join made the centroid more generic, and so the next join easier. Sweeping the grown cut (0.68 / 0.72 / 0.75 / 0.78 / 0.80):
  - **0.75:** the largest US politics thread is still a generic "Republicans · Democrats · Senate" mix (17 items).
  - **0.78:** a 9-item chain of post-midterm op-eds remains.
  - **0.80:** no catch-alls (largest: the Anthropic IPO, 9 items). The Ukraine war (13 items), the summit (23) and the Nvidia scandal (10) each form one thread.
- No "too-common name" rule is needed: the entity boost is capped at +0.06, and the grown cut alone stops the Trump catch-all.

**Thread rescue** (Phase 2): an item scoring within 0.05 below its topic's relevance threshold (§6.4), for the most lenient source that carried it, is kept anyway if its best match is an **active** thread scoring ≥ `T_high`. It never creates a thread. The similarity is stored as `thread_score`, so the export can apply the rule from stored data. Short or terse headlines that belong to a story already being followed shouldn't be lost to the threshold.

### 6.6 Rank and cap
`importance = relevance × source_weight × (1 + 0.3·ln(1 + corroborating_sources)) × freshness_decay`

`freshness_decay = 0.5^(age_hours / 36)`. Importance depends on the current time, so it's computed at export, never stored.

- **Per-thread daily cap: 5.** Overflow is collapsed behind "+N more", never dropped.
- Flat topics have per-day or per-week caps from config.
- No global cap: on a busy day the feed is simply longer.

### 6.7 Enrich (LLM, optional)
A small, bounded number of calls per run, prioritized in this order:
1. Content-kind labels (reporting / analysis / opinion) and filter checks (§7) for borderline items.
2. Thread assignment tiebreaks (§6.5 step 3).
3. Thread titles for newly promoted threads.
4. Study cards (§8.2).
5. Primers for new politics and world threads (§8.5).

The LLM client takes a provider list (`github_models` → fallbacks). Calls use JSON-schema output, are cached by input hash, and log nothing secret. When the run's budget is exhausted, remaining items get heuristic defaults and are re-queued for the next run.

### 6.8 Export and deploy
Write the static JSON the site reads (`feed/index.json`, `feed/topics/<id>.json`, `feed/threads/<id>.json`). Build the SvelteKit site and deploy to GitHub Pages in the same workflow.

The contract is `pipeline/export/models.py` (`schema_version` **2** since Phase 2a; the app refuses a feed of another version and asks for a reload):
- **Exported items:**
  - Visible, routed to a topic, and carried by an enabled source: disabling a source hides its stored items on the next run.
  - Not title-excluded by every source that carried them (`title_exclude`, §6.2).
  - Passing the relevance threshold, or **rescued**: in the rescue band and attached to a listed thread with `thread_score ≥ T_high` (§6.5). A thread that cools keeps what it rescued.
  - Each item `{id, title, url, source_id, published_at, first_seen_at, excerpt, importance, also_covered_by, collapsed}`; titles cleaned and stripped by the item's own source's `title_strip` (§6.2).
- `feed/index.json`: `generated_at`; groups → topics `{id, name, mode, has_sources, visible_count, collapsed_count, latest_first_seen_at}` (thread items counted too); sources `{id, name, type, status, lean, kind, paywall}`.
- `feed/topics/<id>.json`:
  - `threads`: the topic's **listed** threads (active, cooling, dormant; not pending or archived) with at least one exported item, newest update first. Each summary is `{id, title, kind, state, last_item_at, item_count, collapsed_count, latest_first_seen_at, first_seen, latest}`. `first_seen` lists the shown items' `first_seen_at` (for "N new"); `latest` is the newest item, for a preview. Not limited to the lookback, so dormant threads still list.
  - `days`: the other items within the topic's lookback, grouped by UTC day of publication (newest first) and ranked by importance. For flat topics that's every item; for threaded ones, pending single items and unthreaded ones.
- `feed/threads/<id>.json`: `{id, topic_id, title, kind, state, created_at, last_item_at, days}` with every exported item of the thread among the loaded items (≈ 30 days), by UTC day, ranked by importance. Stale topic and thread files are removed.
- Days are UTC in the export; the frontend regroups items by the viewer's local day for display. Per-day caps still count UTC days, so a local day can show slightly more than one day's cap.
- **Caps:**
  - Topic `days`: `max_per_day` per day; `max_per_week` / `target_per_week` over the trailing 7 days, `max_per_month` over 30; otherwise `defaults.daily_cap_per_thread` per day.
  - Thread files: the per-thread daily cap, `daily_cap_per_thread` (topic override, else default 5).
  - Over-cap items are exported with `collapsed: true` and never dropped.

## 7. Filters and labels

Global filters (on for every topic unless the topic opts out):

| Filter | Catches |
|---|---|
| `hype` | "This changes everything" posts with no concrete facts or numbers |
| `memes` | Jokes, memes, shitposts |
| `doom` | Doom posting and speculation without evidence |
| `listicles` | "Top 10 …" roundups. **Allowed in Everyday upgrades.** |
| `charged_extremes` | Emotionally charged takes from either political extreme |
| `engagement_bait` | Rage bait, clickbait, LinkedIn-style engagement posts |
| `influencer` | Fitness, career or tech influencer content |
| `obvious_advice` | Generic advice a reasonably informed adult already knows ("sleep more, exercise"). Test: does it give something specific — a number, a dose, a comparison, a named method? |

Implementation: negative embedding anchors first (free), then the LLM checks only borderline items. Filtered items keep a `hidden_reason` and appear on the **Hidden items** screen so filters can be audited and tuned.

Labels shown on cards: **Reporting / Analysis / Opinion / Study / Guide / Listing**, the outlet's political lean for news outlets (from `sources.yaml`) and evidence badges (studies).

## 8. Topic-specific features

### 8.1 Genshin leaks: parked
Moved to §16 (Parked) on 2026-11-22.

### 8.2 Health study cards
- Health items are **articles about studies** from evidence-focused writers (Stronger By Science, Sweat Science, NYT Well, Examine, Harvard Health), not raw study-database searches (`evidence: articles_about_studies`).
- When an article links a paper (DOI, PubMed or journal URL), look up that paper's abstract and metadata (PubMed E-utilities / Crossref) and build the study card from it. No linked paper means no card.
- Card fields: design (RCT, meta-analysis, cohort …), sample size, duration and population; key results **with numbers**; the **claim strength the authors use** ("associated with" vs "caused"); limitations if stated; a link to the paper.
- **Evidence badges:** 🟢 meta-analysis / systematic review / large RCT · 🟡 smaller RCT or large observational study · ⚪ small, pilot, animal or in-vitro study.
- **Overclaim flag:** compare the article's headline claim with the linked paper's abstract; when the headline claims more, show "Headline says *X*; study found *Y*".
- Generated only from the abstract and metadata. If the abstract isn't available, show no card, just the link.
- Emphasis: what the study found, more than personal takeaways.

### 8.3 Tech trackers
- Fixed threads: phones, laptops, headphones & earbuds, wearables, tablets. (No EVs: the owner doesn't follow cars.)
- Each relevant release or review is compared against the owner's private gear list ("vs. what you have"). That comparison is computed in the pipeline; only the comparison text is published, never the raw gear list. **[open]** decide whether even the comparison text should be owner-only (served from the Worker) rather than public.
- Favor in-depth reviews with real testing over roundups.

### 8.4 World news regions and the weekly roundup
- Regions: Americas · Europe (incl. Russia and Ukraine) · Middle East & North Africa · Sub-Saharan Africa · East Asia · South Asia · Southeast Asia (incl. island nations) · Oceania · Global (UN, trade blocs, summits).
- Threads are stories tagged with a region; the UI filters by region.
- **Weekly roundup:** every region's single most important story of the week, even quiet regions.

### 8.5 Primers (politics and world)
- Generated when a thread is promoted to active, grounded in Wikipedia plus the thread's own items, with source links. No ungrounded model memory.
- Shown expanded the first couple of times the owner opens the thread, then collapsed into an "ⓘ Background" button.

### 8.6 Opinion balance (politics)
- Opinion pieces are labeled. When a thread shows opinion, pick pieces from different leans rather than two from the same side.
- Outlet lean comes from published media-bias ratings recorded in `sources.yaml` (verify when curating).

### 8.7 Jobs
Fully separate from Markets; no cross-posting.
- **Listings** (`listings` mode): internships first, new-grad full-time second; any industry with CS, ML or data roles (healthcare, defense, biotech, finance … not only big tech). Target 20–30 per week. Matched against the private profile; badges for **fresh** (posted < 48 h), **less-known company**, and **citizenship/clearance required** when stated. Sources: the SimplifyJobs internship and new-grad lists, HN "Who is hiring?", and (Phase 4) chosen companies' public Greenhouse / Lever / Ashby job boards, polled directly, which also surfaces listings that never trend on aggregators. Companies on Workday aren't supported. Each listing card gets a **"Look up on Glassdoor"** search link for manual research (a link only; nothing is fetched).
- **Job-market news** (threaded, daily): companies changing direction, in-demand skills, salary data, interview trends. Layoffs and hiring freezes are included at lower weight.
- **Job-search guides** (flat): what to practice (LeetCode / NeetCode / system design), systems for finding and applying efficiently, project ideas that build in-demand skills. Networking is low priority; resume formatting low; negotiation out of scope for now.
- **Never** scrape LinkedIn, Glassdoor or Indeed: their terms prohibit it (Glassdoor retired its public API in 2022). LinkedIn-style influencer content is filtered wherever it appears.

### 8.8 Books
`reading_list` mode: high-impact nonfiction widely considered a must-read, and new nonfiction with real buzz on AI, the economy and practical life skills. A few picks a month.

### 8.9 Markets
Fixed threads for the 11 GICS sectors plus economy-wide threads (Fed and rates, inflation and jobs reports, trade and tariffs, major earnings surprises). News only; never buy/sell advice.
- **Panel** (Phase 4, `panel` in `topics.yaml`): daily closes with day and week change for the S&P 500, Nasdaq Composite and Dow, from FRED (`SP500`, `NASDAQCOM`, `DJIA`).
- **[open]** A sector performance grid.

## 9. Frontend

SvelteKit static app, installable PWA, dark mode first, responsive from phone to desktop.

### 9.1 Views
- **Home:** topic groups with "N new" counts per topic; ends with "You're all caught up."
- **Topic:** threads sorted by last update; cooling threads lower; dormant threads grayed and collapsed at the bottom. Flat topics show a ranked list.
- **Thread (catch-up view):** "N updates since <your last visit>", newest first, with a toggle for chronological; primer at the top when applicable; per-day groups with the cap and "+N more".
- **Item card:** title, source, time, labels and badges (🔒 for `paywall: partial | full`), excerpt. Tap → opens the original article. On an installed PWA, out-of-scope links open in the system's in-app browser sheet; on desktop, a new tab.
- **Hidden items:** filtered items with their reasons.
- **Sources:** per-source health and usefulness (§9.4).
- **Settings:** paste the owner token (once per device).

### 9.2 Owner vs visitor
- Everyone sees the same public, read-only site.
- With the owner token present, read state syncs through the Worker, and owner controls appear: refresh now, mute, pin, rename, merge, split, move item.
- Visitors' read marks stay in their own browser only and affect nothing.

### 9.3 Refresh
The app re-fetches the feed JSON every few minutes while open. "Refresh now" (owner) → Worker → GitHub `workflow_dispatch` → about a minute later the new feed appears.

### 9.4 Source report
For each source: items fetched, shown, opened, hidden (by reason), last success and last error. Trial sources are badged in the feed. Used to decide what to keep.
- **Unique items:** the share of a source's shown items that no other source also covered (`also_covered_by` empty). Sources with near-zero unique contribution after 2 weeks are flagged as candidates to cut. This is how the owner decides whether adding more sources (especially job listings) is worth it.

## 10. Hosting, data and security

### 10.1 Storage
- State lives on an orphan `data` branch as JSON/NDJSON: items partitioned by day, `threads.json` (sorted by id), thread centroids as float32 rows in `centroids.npy` named in order by `centroid_ids.json` (only threads that can still be matched), and an LLM cache.
- Fetch state: `http_cache.json` (ETag / Last-Modified per feed URL) and `source_health.json` (per source: last attempt, status, last success, item count, last error, consecutive failures, feed title). All state is written once at the end of a run, so a crashed run never saves validators for items it didn't store.
- Item embeddings are **not** stored (decided 2026-11-22): ~10–20 MB of vectors rewritten by every hourly commit isn't worth it. New items are embedded anyway; any other item that needs a vector (e.g. the one-time thread backfill) is embedded again.
- The `data` branch is squashed periodically (history isn't needed) so the repo stays small.
- Each run checks out `data`, updates it, commits and pushes. Concurrency: workflow-level `concurrency` group so runs never overlap.
- Implementation: `.github/workflows/pipeline.yml` (hourly at :17 + `workflow_dispatch`) uses `.github/scripts/state.sh` to check `data` out as a git worktree (the first run creates the orphan branch) and to commit and push. Pushes are never forced: a run that somehow missed the existing branch is rejected instead of replacing state. Source health timestamps change every run, so `data` gets about one commit per hour until squashing exists.
- Jobs and permissions: `run` (`contents: write`) → `build` (`contents: read`; site built with `BASE_PATH=/<repo>`, feed copied into `build/feed`) → `deploy` (`pages: write`, `id-token: write`). If `run` fails (e.g. invalid config), nothing is deployed and the site keeps the last feed.

### 10.2 Owner Worker (Cloudflare Worker + KV, free tier)
| Endpoint | Purpose |
|---|---|
| `GET/PUT /read-state` | Last-seen timestamps per thread/topic, synced across devices |
| `POST /refresh` | Calls GitHub `workflow_dispatch` using a fine-grained token stored as a Worker secret |
| `GET/POST /overrides` | Thread mute/pin/rename/merge/split/move; read by the pipeline at the start of each run |

Auth: a long random bearer token. CORS limited to the site's origin.

### 10.3 Private profile
- `config/profile.example.yaml` documents the shape. The real content lives in the `PROFILE_YAML` Actions secret (and in a local, gitignored `profile.yaml` for dev).
- It holds the gear list, health context and job-search profile (skills summary, role types, constraints).
- It's used only for scoring and comparisons and is never written to `data` or the site verbatim.

### 10.4 Security checklist
- GitHub push protection on; pre-commit secret scanner; `.gitignore` covers `.env*`, `profile.yaml`, `*.local.*`.
- Workflow permissions are least-privilege per job (`contents: write` only where needed, `models: read`, `pages: write`, `id-token: write`).
- No secrets in logs; mask any derived values.
- Secrets (Actions secrets, needed from Phase 4): `PROFILE_YAML`, `FRED_API_KEY` (market panel), `NYT_API_KEY` (NYT Books API).
- Config validator (`python -m pipeline.config`, in pre-commit and CI): schemas for all three config files, cross-file references, and the principle 7 guard (sources feeding a `spoiler_policy: fail_closed` topic must stay `disabled`). Profile errors show field paths only, never values.

## 11. Free-tier budget

| Service | Use | Note |
|---|---|---|
| GitHub Actions | Hourly pipeline | Free for standard runners on public repos |
| GitHub Pages | Site hosting | Free for public repos |
| GitHub Models | LLM calls | Free, rate-limited; bounded calls per run, results cached |
| Cloudflare Workers + KV | Owner API | Free tier is far above single-user needs |
| Embedding model | Runs on the Actions runner | Free |

If any limit is hit, degrade (fewer LLM calls, longer intervals). Never upgrade to a paid plan without the owner.

## 12. Privacy
The repo and site are public. Topic descriptions are generic. Personal context lives only in the private profile. Read state is stored in the Worker, not in the repo.

## 13. Accessibility and design
Large, readable type; high-contrast dark theme plus a light theme; no layout shift; full keyboard navigation on desktop; reduced-motion support; tap targets ≥ 44 px.

## 14. Roadmap

Only build the current phase.

| Phase | Scope |
|---|---|
| **0. Setup** | Repo, `.gitignore`, pre-commit (secret scan, lint), `AGENTS.md` symlink, config schemas + validator (pydantic), CI running tests + validator. |
| **1. MVP feed** | RSS + Reddit fetch → normalize → dedupe → embed → relevance → **flat** ranked lists per topic → JSON export → SvelteKit PWA on GitHub Pages, hourly. No LLM. Genshin source stays disabled. |
| **2. Threads** | **2a:** thread assignment + lifecycle, per-thread caps, catch-up view (read state in localStorage). **2b:** owner Worker (read sync, refresh, overrides incl. merge). |
| **3. LLM layer** | Content-kind labels, filter checks, thread titles, primers, opinion balance. |
| **4. Special lanes** | Study cards, tech trackers with gear comparison, job listings, world weekly roundup, reading list, source report, Hidden screen. |
| **5. Polish & open source** | Setup docs for forkers, demo mode with sample data, performance and accessibility pass. |

## 15. Open questions
- **[open]** Confirm the AllSides lean for every news/opinion source marked `# AllSides: check` before Phase 3 opinion balancing.
- **[open]** Job listings during grad-school application season: pause or reduce listings until Dec 15?
- **[open]** Whether tracker comparison text should be public or owner-only (§8.3).
- **[open]** A free daily data source for a sector performance grid (§8.9).

## 16. Parked

Designed but not scheduled. Nothing here is on the roadmap (§14) until the owner revives it.

### 16.1 Genshin leaks (parked 2026-11-22)

**Why parked:** Reddit refuses both its JSON and RSS listings to this pipeline (403 and 404 with our User-Agent, 2026-11-22), and approval for the official API is uncertain. A possible future route: follow a Discord announcement channel into a server the owner owns and read it there with a bot (a proper bot account; **never a self-bot**, which breaks Discord's terms).

**If revived:** add the topic and its source back to `config/` (the schema still supports everything below), build the spoiler filter and credibility classification as the first LLM priority (it blocks display), and only then enable the source. CLAUDE.md principle 7 and the validator keep any source feeding a `spoiler_policy: fail_closed` topic disabled until then.

**Topic design** (formerly §8.1):
- Wanted: new characters and banners; character kits and their meta and team implications; impactful gameplay and QoL changes.
- **Never shown:** story leaks; map, region or area specifics and visuals (a bare "a new region is coming" is OK); events; livestreams; codes; patch notes.
- **Credibility tiers:** ✅ beta-confirmed (current beta cycle) · 🟡 reputable leaker (long-range, unconfirmable) · ⚪ unverified · 🚩 fake (hidden). Signals: the subreddit's own reliability flairs (trusted for "reliable"), title keywords, known leaker names (config list), score and upvote ratio, and the share of top comments calling a leak fake or debunked.
- **Spoiler safety (fail closed):** classify title + flair (+ excerpt) before display; hide if spoiler risk isn't confidently low. **No thumbnails or images** for this topic, ever. The Hidden screen shows titles blurred until tapped.
- **Threads:** per version — **Next patch** (concrete) and **Long-range & meta** (speculative, labeled). Both close when that version ships.

**Mode `patch_cycle`** (formerly in §4): two threads per game version, **Next patch** and **Long-range & meta**. Threads close when the patch ships. Thread assignment (formerly in §6.5) routes by credibility: beta-confirmed → **Next patch**; reputable leaker or long-range → **Long-range & meta**.

**Labels:** credibility badges on cards (formerly in §7); the Hidden screen shows this topic's titles blurred until tapped (formerly in §9.1).
