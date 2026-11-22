# Skein — personal news feed

> A skein is a loose coil of threads; the feed is a bundle of story threads.

## What this is

A personal, self-hosted news feed that replaces social-media scrolling. It pulls from sources the owner curates, groups articles into evolving story **threads** inside **topics**, and shows a **finite** feed ("you're all caught up") as a PWA on phone and laptop.

- One owner for now. The site is public and read-only; only the owner can change state.
- Designed to be open-sourced later so anyone can run their own copy from config files.

**Read `docs/DESIGN.md` before any architectural change.** Topics and sources live in `config/`.

## Principles (do not violate)

1. **Finite, not infinite.** No infinite scroll, autoplay, streaks, engagement mechanics or notifications.
2. **The owner curates.** Topics and sources come only from `config/*.yaml`. Never hardcode a source or topic in code.
3. **Link out, never republish.** Store and show headline, source, date, the feed's own short description (truncated to ~300 chars) and the link. Never store or display full article text, and never embed articles in iframes. The one exception is health **study cards**, which summarize a paper's *abstract* (see DESIGN §8.2).
4. **Zero cost.** Free tiers only. If a feature would need money, stop and ask the owner.
5. **The LLM is optional.** The pipeline must finish and produce a usable feed when every LLM call fails (rate limit, outage, no access). LLM features degrade gracefully: keyword thread names, no labels, no primers.
6. **Public-repo safety.** No secrets, tokens or personal data in the repo. Private data lives in the `PROFILE_YAML` GitHub Actions secret and in Cloudflare Worker secrets.
7. **Fail closed on spoilers.** Genshin items that might contain story, map or region spoilers are hidden unless the classifier is confident they're safe. The Genshin source stays disabled until the spoiler filter exists.

## Stack

| Part | Choice |
|---|---|
| Pipeline | Python 3.12 in GitHub Actions (hourly cron + `workflow_dispatch`). `feedparser`, `httpx`, `sentence-transformers` (small CPU embedding model), `numpy`, `pydantic`, `PyYAML` |
| LLM | OpenAI-compatible client → GitHub Models via the built-in `GITHUB_TOKEN` (`permissions: models: read`). Fallback providers configurable. Few calls per run. |
| State | JSON / NDJSON files on the orphan `data` branch (never on `main`) |
| Frontend | SvelteKit + `adapter-static` + PWA (manifest + service worker), TypeScript |
| Hosting | GitHub Pages, deployed by the same workflow |
| Owner API | One Cloudflare Worker + KV: read-state sync, refresh button, thread overrides. Bearer-token auth. |

## Repo layout (target)

```
config/              topics.yaml, sources.yaml, profile.example.yaml
pipeline/            Python package: fetch/, process/, llm/, export/
web/                 SvelteKit app
worker/              Cloudflare Worker (owner API)
docs/                DESIGN.md and other docs
tests/               pipeline tests with recorded fixtures
.github/workflows/   pipeline + deploy workflow
```

`AGENTS.md` is a symlink to this file so other coding assistants read the same rules.

## Commands

```sh
# one-time setup (Python 3.12)
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]" && pre-commit install

python -m pipeline.config        # validate config/*.yaml (+ local config/profile.yaml if present)
pip install -e ".[embed]"        # embedding model deps (torch); tests don't need them
python -m pipeline run --state ../skein-state --out ../skein-site   # one run (live network) + feed JSON
python -m pipeline.sample --out web/static   # offline sample feed from test fixtures (no network/model)
python -m pipeline run --state ../skein-state --embedder hashing   # no model; scores meaningless
python -m pipeline.calibrate --state ../skein-state   # relevance score distribution per topic
pytest                           # tests
pre-commit run --all-files       # gitleaks, ruff, yaml checks, validator, tests
```

```sh
# web (Node ≥ 22.12; from web/)
npm ci
python -m pipeline.sample --out web/static      # (from the repo root) offline sample feed for dev
npm run dev                                     # http://localhost:5173
npm run check && npm test                       # svelte-check + vitest
BASE_PATH=/skein npm run build                  # static site in web/build (feed/ is copied in at deploy)
```

CI (`.github/workflows/ci.yml`) runs the validator, tests and pre-commit, plus a web job (check, test, build), on every push to `main` and every PR.

The hourly pipeline (`.github/workflows/pipeline.yml`) runs on `main` only: fetch → export → push state to the `data` branch (`.github/scripts/state.sh`) → build → deploy to GitHub Pages. Run it by hand from the Actions tab (workflow_dispatch). Workflows are linted by actionlint in pre-commit.

## Working rules for AI assistants

- **Build only what's asked, or what the current roadmap phase in `docs/DESIGN.md` §14 lists.** If something seems useful but isn't specified, propose it in chat; don't build it.
- Don't add a dependency without saying why. Prefer the standard library and the stack above.
- Don't rename config keys or change a data schema without updating `docs/DESIGN.md` and the config validator in the same change.
- Every source fetcher needs timeouts, rate limiting, conditional requests (ETag / Last-Modified), a descriptive User-Agent, and a test against a recorded fixture. Tests never touch the live network.
- The pipeline is idempotent: rerunning on the same inputs never duplicates items.
- Never print secrets in logs. Never write `PROFILE_YAML` contents (or anything derived from it, verbatim) to the `data` branch or the site.
- Before committing: tests, config validator and secret scanner (pre-commit) all pass.
- Ask before deleting data, rewriting history on `main`, or changing hosting.

## Not in scope

Don't build these unless the owner explicitly asks:

- Discord integration or digests
- YouTube content of any kind
- Podcasts or an audio player (deferred past v1)
- AI summaries in place of articles (study cards are the only summaries)
- Storing or displaying full article text; embedding articles in iframes
- Local news
- General gaming news. For Genshin: story leaks, map or region-specific leaks, events, livestreams, redeem codes, patch notes
- Offer-negotiation content
- Tracking job applications
- Multi-user accounts, sign-up, comments or any social features
- Push notifications
- Paid services of any kind
- Scraping sites whose terms prohibit it (e.g. LinkedIn)
