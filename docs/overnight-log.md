# Overnight log: `ui-data` (thumbnails + thread structure)

_Morning summary goes here when the run finishes._

## Setup

- Branch `ui-data`, created off `origin/main` (4a175a1, phase 2b merged) after `git fetch`, in the main checkout (`~/Documents/skein`).
- **Decision:** the request said both "from this folder, create a new branch … and switch to it" (typed) and "create a separate git worktree at ../skein-ui-data" (pasted plan). I followed the typed instruction: a branch in this folder, no worktree. To use a worktree instead later: `git worktree add ../skein-ui-data ui-data`.
- Before switching, the in-progress theme work was committed as WIP on its own branch, `ui-fog-strand` (790b156), as requested earlier. `ui-overhaul` and `ui-fog-strand` are untouched from here on.
- Rules for the run: no push, merge, deploy or wrangler; no secrets; nothing deleted on the `data` branch (only read, via `git show` / `git archive`). Tests, validator and pre-commit must pass before each commit.

## Step A: thumbnails ✅ committed

**What changed**
- `pipeline/fetch/images.py` (new) takes the image URL the feed itself provides, in this order: image `media:content`, `media:thumbnail`, image `<enclosure>`, then the first `<img>` in the entry's own description/content. Article pages are never fetched.
- `RawEntry.image_url` → `Item.image_url` (normalize keeps it only if the source has `images: true`) → `ExportItem.image_url` (exported only while the source **and** the topic allow images, so flipping a flag hides stored images on the next run).
- `sources.yaml`: per-source `images: true|false`, default true (schema + header comment). Topics already had `images` (for the parked spoiler topic); export honours it too.
- **Web:** `ItemCard` has a fixed 72 px square beside the title. It shows the image (`loading="lazy"`, `decoding="async"`, `referrerpolicy="no-referrer"`, `alt=""`), or a quiet tile with the source's initials when the image is missing or fails to load (`onerror`). The source name stays in the byline. Theme tokens only (`--border`, `--muted`, `--radius`). `types.ts` has an optional `image_url`.
- **Docs:** CLAUDE.md principle 3 (image policy); DESIGN §3.1 (Source.images, Item.image_url), §6.1 (capture rules), §6.8 (export field), §9.1 (item card).

**Decisions (conservative, easy to change)**
- **URL cleaning:**
  - http(s) only; `http://` is upgraded to `https://` (the site is https; mixed content would be blocked).
  - Protocol-relative and relative URLs are resolved against the entry link.
  - URLs over 2048 chars are dropped. `data:` / `javascript:` are never accepted.
- **Tracking pixels / icons are skipped:** declared width or height < 40 px, or paths like `pixel`, `/~r/`, `feedburner`, `gravatar`, `emoji`, `/icons/`, `favicon`, `spacer`.
- **Dedupe:**
  - An image belongs to the source shown. When a more trusted source takes over an item, its image (or none) replaces the old one.
  - A corroborating source never changes the image.
  - An item first stored without an image picks up its own source's image once, on the next run that lists it (idempotent: a stored image is never replaced). Existing stored items have no image until their feed lists them again, so expect images to appear gradually over about a day.
- **Fallback when missing:** your note said "styled fallback when missing or broken", so the initials tile shows for missing images too. That keeps every card the same shape. **To show no tile at all when there's no image:** in `ItemCard.svelte`, wrap the `.thumb` div in `{#if item.image_url}`.
- **Reddit:** not checked for images (no Reddit source is enabled; its JSON has a `thumbnail` field if that's wanted later).
- **Schema version:** not bumped. `image_url` is an optional, additive field, and older clients ignore it.
- **Privacy note:** loading an image from the source reveals the reader's IP address to that image host (the same as following a link). `no-referrer` keeps the page URL private. The service worker already ignores cross-origin requests, so images are never cached by the app.

**Verified sources that provide images** (one live fetch of each, via the pipeline's own fetcher, throwaway cache, no state written; script kept outside the repo)
- 51 verified, enabled sources, all fetched OK. **39 provide images** (31 of 39 active, 8 of 12 trial); 36 of them on at least half their entries.
- **No images (12):** hn-frontpage, antigravity-blog, claude-blog, openai-news, anthropic-news, cochrane, reuters-world, reuters-markets (Google News search feeds), fed-monetary, bls-empsit, bls-cpi, five-books.
- Spot-checked URLs from simon-willison, notebookcheck, 9to5mac, stronger-by-science, ap-top (via flipboard CDN), the-dispatch and national-review. All are article images, not icons.

**Tests:** pytest 462 passed (new: `tests/fetch/test_images.py`, plus normalize, dedupe and export cases). Validator OK. Web: svelte-check clean, vitest 95 passed, `BASE_PATH=/skein` build OK. pre-commit all green.

**To check in the morning**
- The real feed after the next run: images arrive gradually as feeds re-list items.
- AP images come through `ic-cdn.flipboard.com` (that feed is flipboard's). Fine to show, but say if you'd rather turn `images: false` on for `ap-top` / `ap-us`.
- The fallback tile on cards without images: keep it, or switch to "no tile" (one line, see above).

## Step B: thread structure

_Not started._
