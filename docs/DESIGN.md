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
  id: string; type: "rss" | "reddit";       // later phases add "pubmed" | "job_board" | "github_list"
  url?: string;                             // rss only
  subreddit?: string;                       // reddit only
  topics: string[];                         // which topics it may feed
  status: "active" | "trial" | "disabled";
  weight: number;                           // 0.5–1.5, manual trust knob (default 1.0)
  lean?: "left" | "center-left" | "center" | "center-right" | "right" | null; // news outlets only
  kind?: "reporting" | "analysis" | "opinion" | "study" | "listing" | "guide"; // default content-kind hint
  verified: boolean;                        // URL checked during curation (default false)
  options?: Record<string, unknown>;        // e.g. reddit min_score
};

type Item = {
  id: string;                 // hash of canonical URL
  source_id: string; url: string; canonical_url: string;
  title: string; excerpt?: string;          // feed-provided, ≤300 chars
  published_at: string; fetched_at: string;
  topic_id?: string; thread_id?: string;
  relevance: number;          // 0–1
  importance: number;         // ranking score, §6.6
  labels: {
    kind?: "reporting" | "analysis" | "opinion" | "study" | "listing" | "guide";
    credibility?: "beta_confirmed" | "reputable_leaker" | "unverified" | "fake";   // Genshin
    evidence?: "strong" | "moderate" | "weak";                                     // studies
    region?: string;          // world news
    flags?: string[];         // e.g. "listicle", "spoiler_risk", "overclaim"
  };
  hidden_reason?: string;     // set when filtered; kept for the review screen
  study_card?: StudyCard;     // §8.2
};

type Thread = {
  id: string; topic_id: string;
  kind: "story" | "tracker" | "question" | "patch" | "fixed";
  title: string;              // LLM-named, or keyword fallback
  state: "pending" | "active" | "cooling" | "dormant" | "archived";
  created_at: string; last_item_at: string;
  centroid: number[];         // embedding centroid (stored separately, §10.1)
  item_ids: string[];
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
| `patch_cycle` | Two threads per game version: **Next patch** and **Long-range & meta**. Threads close when the patch ships. | Genshin leaks |
| `fixed` | Predefined threads only (no automatic creation). | Markets (sectors + economy-wide) |
| `listings` | Job listings matched to the private profile, with a weekly target count. | Jobs: listings |
| `reading_list` | Slow lane, a few picks a month. | Books |

## 5. Thread lifecycle

```
pending ──(2+ items or high importance)──▶ active ──(no items N days)──▶ cooling ──▶ dormant ──▶ archived
                                              ▲                                        │
                                              └──────── new matching item ◀────────────┘
```

- **pending:** a new thread with one item. Shown inline as a single item and only promoted to a thread when a second item arrives within 72 h, or when the first item's importance is very high. This prevents a flood of one-item threads.
- **cooling:** sinks in the topic list.
- **dormant:** grayed out and collapsed at the bottom of the topic.
- **archived:** hidden; searchable.
- A dormant or archived thread **revives** when a new item matches it, keeping its full history.
- Timings are per topic (`dormant_after_days`, `archive_after_days`). Defaults: politics 7–14 days; AI ~21; trackers and fixed threads never.

**Owner overrides** (stored by the Worker, applied at the start of each pipeline run): rename, pin, mute, merge two threads, split items out to a new thread, move an item to another thread.

## 6. Pipeline

Runs hourly in GitHub Actions, plus on demand via the refresh button (§9.2). Each run is idempotent.

```
fetch → normalize → dedupe → embed → relevance → classify/filter → assign thread → rank & cap → enrich (LLM) → export → deploy
```

### 6.1 Fetch
- Conditional GET (ETag / Last-Modified); unchanged feeds cost nothing.
- Per-host rate limits, timeouts, retries with backoff, descriptive User-Agent.
- Reddit via its public RSS/JSON endpoints, which may be rate-limited or blocked from cloud runners. A source failure must not fail the run; it's recorded in source health (§9.4).
- Source types for v1: `rss`, `reddit`. Later: `pubmed`, `job_board` (Greenhouse / Lever / Ashby public job-board APIs), `github_list` (community internship lists).

### 6.2 Normalize
Canonicalize URLs (strip tracking params), parse dates to UTC, trim the excerpt to ≤300 chars, and drop items older than the topic's lookback window.

### 6.3 Dedupe
1. Exact: canonical URL hash.
2. Near-duplicate: title-embedding cosine ≥ 0.92 within 48 h → keep the higher-weight source, record the others as `also_covered_by` (used as a corroboration signal in ranking).

### 6.4 Embed and relevance
- Small CPU embedding model (e.g. `bge-small-en-v1.5` or `all-MiniLM-L6-v2`), cached between runs with the Actions cache.
- Each topic's `description` + `include` examples are embedded as positive anchors, and its `exclude` examples as negative anchors.
- `relevance = sim(item, positives) − λ·sim(item, negatives)`. Items below the topic threshold are dropped. Items from sources mapped to several topics go to the best-scoring one.
- For job listings and gear trackers, the private profile adds an extra similarity term (§10.3).

### 6.5 Thread assignment (threaded / question / tracker / patch_cycle)
For each relevant item in a threaded topic:
1. Candidates: the topic's threads (any state except archived), ranked by cosine(item, thread centroid), with a boost for overlapping named entities.
2. Top score ≥ `T_high` (start at 0.75) with a clear margin → attach.
3. Between `T_low` (0.55) and `T_high` → ask the LLM to pick among the top 3 or "new thread". If the LLM is unavailable: attach if ≥ 0.65, else new.
4. Otherwise → new `pending` thread.
5. Update the centroid as a recency-weighted average.

Mode-specific rules:
- `tracker` and `fixed`: assign only to the predefined threads (nearest by similarity); never create new ones.
- `patch_cycle`: route by credibility. Beta-confirmed → **Next patch**; reputable-leaker or long-range → **Long-range & meta**.
- Thresholds are tuned against a small hand-labeled set in `tests/fixtures/threading/`.

### 6.6 Rank and cap
`importance = relevance × source_weight × (1 + 0.3·log(1 + corroborating_sources)) × freshness_decay`

- **Per-thread daily cap: 5.** Overflow is collapsed behind "+N more", never dropped.
- Flat topics have per-day or per-week caps from config.
- No global cap: on a busy day the feed is simply longer.

### 6.7 Enrich (LLM, optional)
A small, bounded number of calls per run, prioritized in this order:
1. Genshin spoiler / credibility classification (blocks display).
2. Content-kind labels (reporting / analysis / opinion) and filter checks (§7) for borderline items.
3. Thread assignment tiebreaks (§6.5 step 3).
4. Thread titles for newly promoted threads.
5. Study cards (§8.2).
6. Primers for new politics and world threads (§8.5).

The LLM client takes a provider list (`github_models` → fallbacks). Calls use JSON-schema output, are cached by input hash, and log nothing secret. When the run's budget is exhausted, remaining items get heuristic defaults and are re-queued for the next run.

### 6.8 Export and deploy
Write the static JSON the site reads (`feed/index.json`, `feed/topics/<id>.json`, `feed/threads/<id>.json`). Build the SvelteKit site and deploy to GitHub Pages in the same workflow.

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

Labels shown on cards: **Reporting / Analysis / Opinion / Study / Guide / Listing**, the outlet's political lean for news outlets (from `sources.yaml`), credibility badges (Genshin) and evidence badges (studies).

## 8. Topic-specific features

### 8.1 Genshin leaks
- Wanted: new characters and banners; character kits and their meta and team implications; impactful gameplay and QoL changes.
- **Never shown:** story leaks; map, region or area specifics and visuals (a bare "a new region is coming" is OK); events; livestreams; codes; patch notes.
- **Credibility tiers:** ✅ beta-confirmed (current beta cycle) · 🟡 reputable leaker (long-range, unconfirmable) · ⚪ unverified · 🚩 fake (hidden). Signals: the subreddit's own reliability flairs (trusted for "reliable"), title keywords, known leaker names (config list), score and upvote ratio, and the share of top comments calling a leak fake or debunked.
- **Spoiler safety (fail closed):** classify title + flair (+ excerpt) before display; hide if spoiler risk isn't confidently low. **No thumbnails or images** for this topic, ever. The Hidden screen shows titles blurred until tapped.
- **Threads:** per version — **Next patch** (concrete) and **Long-range & meta** (speculative, labeled). Both close when that version ships.

### 8.2 Health study cards
- Prefer primary sources (study databases, journals) over health news.
- Card fields: design (RCT, meta-analysis, cohort …), sample size, duration and population; key results **with numbers**; the **claim strength the authors use** ("associated with" vs "caused"); limitations if stated; a link to the paper.
- **Evidence badges:** 🟢 meta-analysis / systematic review / large RCT · 🟡 smaller RCT or large observational study · ⚪ small, pilot, animal or in-vitro study.
- **Overclaim flag:** when a news article links a study and its headline claims more than the abstract supports, show "Headline says *X*; study found *Y*".
- Generated only from the abstract and metadata. If the abstract isn't available, show no card, just the link.
- Emphasis: what the study found, more than personal takeaways.

### 8.3 Tech trackers
- Fixed threads: phones, laptops, headphones & earbuds, wearables, tablets, EVs (low priority).
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
- **Listings** (`listings` mode): internships first, new-grad full-time second; any industry with CS, ML or data roles (healthcare, defense, biotech, finance … not only big tech). Target 20–30 per week. Matched against the private profile; badges for **fresh** (posted < 48 h), **less-known company**, and **citizenship/clearance required** when stated. Sources: community-maintained internship lists and companies' public job-board APIs, polled directly. Polling boards directly also surfaces listings that never trend on aggregators.
- **Job-market news** (threaded, daily): companies changing direction, in-demand skills, salary data, interview trends. Layoffs and hiring freezes are included at lower weight.
- **Job-search guides** (flat): what to practice (LeetCode / NeetCode / system design), systems for finding and applying efficiently, project ideas that build in-demand skills. Networking is low priority; resume formatting low; negotiation out of scope for now.
- LinkedIn is never scraped (its terms prohibit it). LinkedIn-style influencer content is filtered wherever it appears.

### 8.8 Books
`reading_list` mode: high-impact nonfiction widely considered a must-read, and new nonfiction with real buzz on AI, the economy and practical life skills. A few picks a month.

### 8.9 Markets
Fixed threads for the 11 GICS sectors plus economy-wide threads (Fed and rates, inflation and jobs reports, trade and tariffs, major earnings surprises). News only; never buy/sell advice. **[v2]** a sector performance panel, if a reliable free daily data source exists.

## 9. Frontend

SvelteKit static app, installable PWA, dark mode first, responsive from phone to desktop.

### 9.1 Views
- **Home:** topic groups with "N new" counts per topic; ends with "You're all caught up."
- **Topic:** threads sorted by last update; cooling threads lower; dormant threads grayed and collapsed at the bottom. Flat topics show a ranked list.
- **Thread (catch-up view):** "N updates since <your last visit>", newest first, with a toggle for chronological; primer at the top when applicable; per-day groups with the cap and "+N more".
- **Item card:** title, source, time, labels and badges, excerpt. Tap → opens the original article. On an installed PWA, out-of-scope links open in the system's in-app browser sheet; on desktop, a new tab.
- **Hidden items:** filtered items with their reasons (Genshin titles blurred).
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

## 10. Hosting, data and security

### 10.1 Storage
- State lives on an orphan `data` branch as JSON/NDJSON: items partitioned by day, `threads.json`, centroids as `.npy`, and an LLM cache.
- Fetch state: `http_cache.json` (ETag / Last-Modified per feed URL) and `source_health.json` (per source: last attempt, status, last success, item count, last error, consecutive failures, feed title). All state is written once at the end of a run, so a crashed run never saves validators for items it didn't store.
- Only the last ~30 days of item embeddings are kept.
- The `data` branch is squashed periodically (history isn't needed) so the repo stays small.
- Each run checks out `data`, updates it, commits and pushes. Concurrency: workflow-level `concurrency` group so runs never overlap.

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
| **2. Threads** | Thread assignment + lifecycle, per-thread caps, catch-up view, owner Worker (read sync, refresh, overrides). |
| **3. LLM layer** | Content-kind labels, filter checks, thread titles, Genshin credibility + spoiler filter (then enable the Genshin source), primers, opinion balance. |
| **4. Special lanes** | Study cards, tech trackers with gear comparison, job listings, world weekly roundup, reading list, source report, Hidden screen. |
| **5. Polish & open source** | Setup docs for forkers, demo mode with sample data, performance and accessibility pass. |

## 15. Open questions
- ~~Final project name~~: **Skein** (decided 2026-11-21).
- **[open]** Source curation, with feed URLs verified: the next working session.
- **[open]** Job listings during grad-school application season: pause or reduce listings until Dec 15?
- **[open]** Whether tracker comparison text should be public or owner-only (§8.3).
- **[open]** A free daily market-data source for the v2 sector panel.
