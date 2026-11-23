# Overnight log: `ui-data` (thumbnails + thread structure)

## Morning summary

Both steps are done and committed on `ui-data` (off `origin/main`). Nothing was pushed, merged or deployed, and the `data` branch was only read.

- **Step A, thumbnails ✅**
  - Cards now show the image the feed itself provides, loaded from the source (`lazy`, `no-referrer`). When there's no image, or it fails to load, a quiet tile with the source's initials takes its place.
  - Per-source `images: true|false` (default true). Policy written into CLAUDE.md principle 3 and DESIGN.
  - **39 of 51 verified sources provide images.**
- **Step B, thread structure ✅**
  - Each thread file now carries `structure: {spine, branches[{id, anchor, items}], related[{id, title, topic_id, similarity}]}`, from embedding storylines (average-linkage clustering) and thread-centroid similarity.
  - Thresholds are config values in `topics.yaml` `defaults.structure`, picked from the real stored data: link 0.72, link_predefined 0.65, anchor_day_penalty 0.15, related 0.80, related_max 5, min_items 3, min_branch_items 1 / min_branch_items_predefined 2 (added after review). Documented in DESIGN §6.9.
  - On real data: 23 of 104 threads have branches (40 branches), and 47 have related threads. **20 examples are below for review** (generated before the folding rule; tracker and fixed threads now keep only their 2+ item branches).
- **Please look at:**
  - The 20 examples (do the spines and branches match your sense of the stories?).
  - The initials-tile fallback on cards without images.
  - AP images coming via flipboard's CDN.
- **Tests:** pytest 475, web vitest 95, svelte-check clean, build OK, validator OK, pre-commit green, before each commit.
- The web view doesn't use `structure` yet (that's the Fog & Strand thread view's job). The field is exported and typed in `web/src/lib/types.ts`.


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

## Step B: thread structure ✅ committed

**What changed**
- `pipeline/process/structure.py` (new, pure, deterministic):
  - Storylines by average-linkage clustering of a thread's item vectors (title + excerpt, the same text thread assignment embeds).
  - The spine is the largest storyline (ties: longest span, then earliest). Every other storyline is a branch, anchored to the spine item maximizing `cos − anchor_day_penalty × days apart`.
  - Related threads come from thread-centroid cosine.
- **`run.py`:** after thread assignment and save, structure is computed for every listed (active / cooling / dormant, not muted) thread. Vectors already computed this run are reused, and the model loads only if something else needs embedding. On any failure it logs and exports without structure (LLM-free, degrades to a timeline).
- **Export:** `threads/<id>.json` gains `structure`, projected onto the exported items:
  - Unexported items are dropped. A branch whose anchor isn't exported moves to the nearest exported spine item in time.
  - Unplaced exported items join the spine, and with no spine left everything is spine.
  - Related threads list only exported threads, with their exported (renamed) titles.
  - The field is additive, so the schema stays at version 2. Web types are updated (`ThreadStructure`, `StructureBranch`, `RelatedThread`).
- **Config:** a required `defaults.structure` block (schema + validator + repo and fixture `topics.yaml`).
- **Small refactor:** `LISTED_STATES` moved to `pipeline/models.py`, so process and export share one definition.
- **Docs:** DESIGN §6.8 (thread file fields) and new §6.9 (algorithm, parameters, tuning notes).

**How the thresholds were picked** (read-only copy of `origin/data` via `git archive` into the scratchpad; real model, offline from the local cache)
- **Data:** 1342 stored items over two days (2026-11-22/23); 104 listed threads holding 425 visible items. The largest thread has 28 items.
- **Within-thread pairwise cosine:** story / question median 0.72 (p25 0.68, p75 0.77); tracker / fixed median 0.62 (p25 0.57, p75 0.69).
- **`link` sweep, threads ≥ 3 items** (threads with branches / storylines per thread / median spine share):

  | link | with branches | storylines per thread | median spine share |
  |---|---|---|---|
  | 0.65 | 13 of 45 | 2.2 | 1.0 |
  | 0.70 | 20 | 3.1 | 0.80 |
  | **0.72** | **24** | **3.5** | **0.75** |
  | 0.75 | 31 | 4.2 | 0.67 |
  | 0.80 | 28 | 5.3 | 0.33 |

  Reading the actual headlines: at 0.70 real side stories (the nuclear-arms thread inside the Trump–Xi–Putin summit) get absorbed into the spine; at 0.75 spines fragment into near-duplicates. **0.72 chosen.**
- **`link_predefined`:** tracker and fixed threads are broad by design. At 0.72 they splintered into 69 branches (60 single items, with branches piling onto a few anchors). 0.65 gives 47 branches with real side stories (the Nvidia–China chips storyline in Information Technology). 0.62 flattens Phones into a single spine. **0.65 chosen.**
- **`anchor_day_penalty`:** it barely matters for story threads (their anchors are already spread out), but for broad threads it pulls anchors toward the branch's own time (median gap 15 h → 11 h). **0.15 per day chosen.** With two days of data this can't be tuned further yet.
- **`related`:** the thread-centroid cosine over 5356 pairs has median 0.58, p95 0.74, p99 0.84.
  - ≥ 0.80 pairs are reliably the same subject: COP31 ↔ UN climate talks, Nvidia–China ↔ Silicon Valley, the summit ↔ its us-politics twin.
  - 0.75–0.80 is mixed. Below that it's mostly coincidence.
  - **0.80 chosen (96 pairs; 54 of 104 threads with at least one), `related_max` 5.**
- **Sibling rule:** market sectors (predefined threads of the same fixed topic) scored 0.81–0.86 with each other just by being "market news", so siblings are never related to each other. The rule is a few lines in `related_threads` if you'd rather keep them.
- **Cost:** model load 3.2 s, then embedding and structure for 425 items 1.7 s (laptop CPU). On the GitHub runner it should be a few seconds more. The model now loads on every exporting run, even one with no new items.

**Decisions (conservative, easy to change)**
- **Not stored:** structure is recomputed each run from stored items. That keeps it idempotent and lets owner merges, splits and moves show at once, at the cost of a few seconds and the model load every run.
- **Branch ids:** `b-<first item id>`. They're stable while the same item leads the branch, so they can carry future LLM names or owner overrides.
- **One-item branches are kept.** In story threads they're usually real asides; in markets threads they're mostly noise from routing (see open questions).
- **Related threads can be in any topic** (the summit's twin lives in us-politics). Only exported (listed, not muted) threads appear.

**Open questions**
- **Market sector routing:** some fixed market threads hold off-subject items (the Health Care sector thread is mostly Anthropic-IPO stories). That's thread assignment's nearest-anchor routing, not structure, but it makes those threads' branches look odd. Worth a look at the sector descriptions in `topics.yaml`.
- **One-item branches in tracker / fixed threads:** keep, or fold them into the spine? It would be a `min_branch_items` setting.
- **Retuning:** with only two days of data, re-run the sweep after a couple of weeks. The scratch scripts weren't committed; ask and I'll turn them into `python -m pipeline.calibrate structure`.

**Tests:** pytest 475 passed (new: `tests/process/test_structure.py` covering clustering, no chaining, spine choice, anchoring, fallbacks, predefined link, related threads and siblings, and orchestration; the export projection and re-anchoring; an end-to-end sample run where every exported item is placed exactly once). Validator OK. Web: svelte-check clean, vitest 95, build OK. pre-commit all green.

### Example structures (20, from the real data, final config)

Totals: 104 listed threads; 27 have branches (73 branches, 54 of them single items); 47 have related threads.

**1. Phones** (tech-trackers, tracker, 28 items, 6 branches)
- Spine:
  - Why iPhone Duo wasn’t for me (but might be for you)
  - Leaker claims Apple developing four models of 20th anniversary iPhone
  - Apple announces 2026 App Store Award finalists
  - iPhone 18, iPhone Air 2 get new release timing updates
  - iPhone Duo is getting three new features in iOS 27.3
  - Apple Creator Studio adds MotionVFX for Final Cut Pro, new Pixelmator Pro features, more
  - Apple releases HomeView 27.2.1 update, here’s what’s new
  - New leaks detail next year’s iPhone Pro redesign and iPhone Duo 2
  - iOS 27.3 beta can cause HomeView issues, Apple confirms
  - HomeView woes, iPhone Duo face unlock, macOS Full Disk Access changes
  - Next year’s iPhone Pro redesign sounds like exactly what I’ve been wanting
  - iPadOS 27.3, watchOS 27.3, more get public beta 2, here’s what’s new
  - iPhone Air 2 dummy unit shows off new dual-camera design
  - iOS 27.3: New features, release date, more
  - Apple Calendar got two feature upgrades it really needed in iOS 27
  - iOS 27 has clever new Messages feature I’ve been using a lot
  - 9to5Mac Overtime 091: Kicking the tires and seeing what works
  - Not upgrading to iPhone 18 Pro or Duo? Here’s what’s coming in 2027
  - iOS 27: My favorite new iPhone features (other than AI)
- Branch off “Why iPhone Duo wasn’t for me (but might be for you)”:
  - iCloud, App Store, and other Apple services hit by ongoing outage [U]
  - WhatsApp’s first-party chat history backup service moves ahead
- Branch off “Why iPhone Duo wasn’t for me (but might be for you)”:
  - Report: iPhone set to gain market share in 2027 amid industry-wide slump
- Branch off “Apple releases HomeView 27.2.1 update, here’s what’s new”:
  - iFixit tears down Apple HomeView, finds lots of glue and endless frustration
- Branch off “iPhone Duo is getting three new features in iOS 27.3”:
  - The Android camera app that doesn’t overprocess adds new color grading sets, expands to iPhone
  - Halide camera app just got even better for iPhone Duo
  - The Xiaomi 18 Pro proves two screens aren’t better than one
- Branch off “iPadOS 27.3, watchOS 27.3, more get public beta 2, here’s wh”:
  - OpenAI begins testing dots with ChatGPT Plus users, expands Business access
- Branch off “Not upgrading to iPhone 18 Pro or Duo? Here’s what’s coming ”:
  - A price drop for the Samsung phone changes everything: Galaxy S26 FE reviewed
- Related: none

**2. Trump · Putin · Summit · Xi** (world-news, story, 24 items, 5 branches)
- Spine:
  - Steve Rosenberg: Historic talks with Xi and Trump are a coup for Putin
  - This is a remarkable diplomatic moment for China's Xi - but it comes with pitfalls
  - Behind Trump Meeting, Xi and Putin Share a Vision of Usurping U.S. Power
  - At Summit With Xi and Putin, Trump Seeks to Project Power Abroad While Sharing It at Home
  - BBC correspondents discuss what Trump, Xi and Putin got out of historic talks
  - Trump-Xi Summit Shows Putin’s Powerful Friendships Have Their Limits
  - An Overhyped Trilateral Summit
  - Putin Exits Summit With Symbolic Win, Saying He and Trump Share ‘Values’
  - Trump Flaunts Camaraderie With Xi and Putin but Has Little to Show for It
  - What Trump’s Summit in China Reveals
  - America’s Slide Into an Amoral Foreign Policy
- Branch off “Steve Rosenberg: Historic talks with Xi and Trump are a coup”:
  - Inside Xi Jinping’s Grip on Power Ahead of Trump Talks
- Branch off “Steve Rosenberg: Historic talks with Xi and Trump are a coup”:
  - Trump’s Nuclear Gambit with Xi and Putin
  - How Trump Can Avoid a Global Nuclear Arms Race
  - Putin, Trump and Xi Condemn Nuclear War as Europe Watches Closely
  - Xi Jinping’s Say-Nothing Summit
  - Opinion / Nuclear Peace in Our Time. Not
- Branch off “BBC correspondents discuss what Trump, Xi and Putin got out ”:
  - Trump, Xi, Putin End Historic Summit With Denunciation of Nuclear War
- Branch off “Trump Flaunts Camaraderie With Xi and Putin but Has Little t”:
  - At APEC Summit, U.S., China and Russia Vow to Increase Oil Supply Amid Global Energy Transition
- Branch off “Trump Flaunts Camaraderie With Xi and Putin but Has Little t”:
  - The Latest: Trump says Putin wants to end war despite Russia rejecting Kushner’s claims of prog
  - Trump defends calling Putin a friend but says he ‘can’t speak’ to whether he's a friend to the
  - Zelensky says Putin is a 'killer' after Trump calls Russian leader a friend
  - Opinion / Vladimir Putin’s Existential Fight for Ukraine
  - Opinion / Excusing ‘My Friend’ Vladimir
- Related: Trump · Conference (us-politics, 0.91); China · Nvidia · Xi · Scandal (world-news, 0.82); The Broken Promises Behind Trump’s Tariffs (world-news, 0.81); JD Vance Should Not Be Finger-Pointing in the Midst of War (world-news, 0.81); Rescue Mission (world-news, 0.80)

**3. Information Technology** (markets, fixed, 22 items, 3 branches)
- Spine:
  - The Investors Set to Win Big in Anthropic’s IPO
  - The Bond Market’s Surprising Take on the AI Trade
  - Tech giants will reap giant paydays from Anthropic’s I.P.O. But a fraudster’s shares are long g
  - Anthropic’s IPO Mints New Millionaires
  - Anthropic’s Mega IPO Lives Up to Wall Street Hype but Fails to Revive AI Trade
  - This Billionaire Just Made a Bundle Off A.I. But It Could Have Been More.
  - Asian Equities Tumble as AI Stock Selloff Deepens
  - European Tech Stocks Tumble as AI Selloff Intensifies
  - Stock Market News, Nov. 20, 2026: Tech Rout Deepens as Nvidia, Anthropic Slide
  - Anthropic Shares Are a Rational Bet on the Next Phase of AI
  - Can Anthropic Revive the A.I. Trade?
  - Anthropic’s I.P.O. Turns Tech Researchers Into Overnight Millionaires
  - Tech Rout Deepens as Anthropic Stock Slides
  - U.S. Stocks Extend Plunge as AI Boom Turns to Bust
  - Anthropic’s IPO Turmoil Caps $4 Trillion AI Wipeout on Wall Street
  - Anthropic’s Debut Shows the Disconnect Between Wall Street and Silicon Valley
- Branch off “The Investors Set to Win Big in Anthropic’s IPO”:
  - Big Tech Needs to Spread Its Bets on Data Centers
- Branch off “The Investors Set to Win Big in Anthropic’s IPO”:
  - Trump Administration Moves to Close A.I. Chip Loophole Ahead of China Trip
  - Wall Street Pledged to Mobilize $500 Billion for Nvidia—but Hasn’t Put Up a Dime
  - Nvidia Asked to Sell Chips to Companies Tied to Chinese Military and Megaspeed
  - Scott Bessent Calls on Nvidia to Provide Answers on Chip Sales to China
- Branch off “European Tech Stocks Tumble as AI Selloff Intensifies”:
  - European stocks recover after steep technology-led selloff
- Related: Anthropic · IPO · Future · AI (us-politics, 0.93); China · Nvidia · Xi · Scandal (world-news, 0.86); Silicon · Valley (us-politics, 0.85); Anthropic · Initial · Public · Offering (ai-news, 0.84); What’s So Important About Nvidia’s Chips? (us-politics, 0.82)

**4. Ukraine · Strikes · Russian · Bridge** (world-news, story, 17 items, 3 branches)
- Spine:
  - Ukrainian Strike Severs Part of Russia’s Crimean Bridge
  - 'The drones don't fly here' - BBC reports from Ukraine's new front line
  - Why Ukraine’s Kerch Bridge Strike Matters
  - Russia targets Kyiv crossings days after Ukraine hits Crimean Bridge
  - Russia Steps Up Attacks on Kyiv’s Bridges
  - What we know about the latest Russian missile strikes on Ukraine
  - Russia-bound ship attacked in Gulf of Finland
  - Suspected Ukrainian sea drones hit Russian warship at Benghazi naval base, Libyan officials say
  - Two Russian Ships Attacked Far From Ukraine
  - Ukraine Claims Strikes on Russian Ships Near Libya
- Branch off “Ukrainian Strike Severs Part of Russia’s Crimean Bridge”:
  - Why the Ukraine War Is Working for Putin
  - The War Is Ravaging Ukraine’s Wildlife, Too
- Branch off “Why Ukraine’s Kerch Bridge Strike Matters”:
  - After Bridge Attack, Putin Says He Will ‘Not Be Negotiating’ Ukraine Cease-Fire
- Branch off “Russia-bound ship attacked in Gulf of Finland”:
  - Ballistic missile attack on Zelenskyy's hometown in central Ukraine kills 2 and wounds scores
  - In Ukraine, the fight to keep winter outside begins with a broken window
  - Russian attack near Ukraine's capital strikes apartment building, killing 3 and burying others
  - 'Danger seems greater all the time': Ukrainians search for missing after Russian strikes
- Related: Russian · Poland (world-news, 0.85)

**5. Major earnings surprises** (markets, fixed, 16 items, 6 branches)
- Spine:
  - Stocks Skid Into a Correction, as A.I. Worries Intensify
  - Has the AI Bubble Already Burst?
  - S&P 500 Futures Rise After Tough Week
  - Stock Futures Rally as Dust Settles After AI-Driven Selloff
  - Stock Market Today: Stock Futures Point to Recovery After Friday’s Bloodbath
- Branch off “Stocks Skid Into a Correction, as A.I. Worries Intensify”:
  - Stocks Down Just Ahead of Nvidia’s Earnings Report
  - Stocks Often Prosper After an Abrupt C.E.O. Exit. Is Nvidia Different?
  - Nvidia Said to Face S.E.C. Probe Into Its Accounting Practices
- Branch off “Stocks Skid Into a Correction, as A.I. Worries Intensify”:
  - What You Should Know About Downdetector Before the Next Big Tech Outage
- Branch off “Stocks Skid Into a Correction, as A.I. Worries Intensify”:
  - Two Big Debuts Fail To Boost Stocks
- Branch off “Stocks Skid Into a Correction, as A.I. Worries Intensify”:
  - WSJ Dollar Index Rises to New 52-Week High
  - WSJ Dollar Index Rises 0.42% This Week to 98.75
  - How the WSJ Determined Mark Walter’s Total Borrowing
- Branch off “S&P 500 Futures Rise After Tough Week”:
  - Asian Currencies Mixed as Traders Digest Divergent Signals
- Branch off “S&P 500 Futures Rise After Tough Week”:
  - Some Underperforming Japan Stocks May Start Rising After Strong Results
  - Julius Baer Profit Climbs as Inflows Boost Assets Under Management
- Related: A 10% drop for the stock market is unnerving, but it's not that unusual (us-politics, 0.85); Anthropic · IPO · Future · AI (us-politics, 0.80)

**6. Financials** (markets, fixed, 14 items, 8 branches)
- Spine:
  - SEC Is Probing Nvidia Amid Departure of CEO Jensen Huang
  - Nvidia’s Strong Fundamentals Give New CEO a Much-Needed Tailwind
  - Jensen and Lori Huang Have Amassed a Vast Fortune. We Break Down Their Wealth.
- Branch off “SEC Is Probing Nvidia Amid Departure of CEO Jensen Huang”:
  - Deutsche Bank Shares Drop After Leaks Put Spotlight on Troubled Past
  - JPMorgan Chase Customer Data Is Exposed in Latest Hack
  - Visa, Mastercard and JPMorgan Customer Data Leaked by Hackers
- Branch off “SEC Is Probing Nvidia Amid Departure of CEO Jensen Huang”:
  - JPMorgan Chase Names Bregje de Best to Succeed Jeremy Barnum as CFO
- Branch off “Nvidia’s Strong Fundamentals Give New CEO a Much-Needed Tail”:
  - Mamdani, Musk, Altman, A.I. and Other DealBook Summit Highlights
- Branch off “Nvidia’s Strong Fundamentals Give New CEO a Much-Needed Tail”:
  - Canada’s Banking Regulator Moves to Level Playing Field for Smaller Lenders
- Branch off “Nvidia’s Strong Fundamentals Give New CEO a Much-Needed Tail”:
  - British Bank Backed by Kushner’s Affinity Gets U.S. License
- Branch off “Nvidia’s Strong Fundamentals Give New CEO a Much-Needed Tail”:
  - China’s A.I. Ambitions Are Running Into a Money Problem
- Branch off “Jensen and Lori Huang Have Amassed a Vast Fortune. We Break ”:
  - 11 of the Best Financial Advisor Companies: Well-Known Fiduciary Investment Firms to Consider
  - 5 of the Top Financial Advisor Companies for Retirees: Well-Known Fiduciary Firms to Consider
- Branch off “Jensen and Lori Huang Have Amassed a Vast Fortune. We Break ”:
  - Citi Undercounted $35 Billion in Assets at U.K. Subsidiary
- Related: China · Nvidia · Xi · Scandal (world-news, 0.85); Jensen · Alice · Huang · Nvidia (us-politics, 0.85); Silicon · Valley (us-politics, 0.81); Anthropic · IPO · Future · AI (us-politics, 0.80)

**7. Energy** (markets, fixed, 10 items, 5 branches)
- Spine:
  - The Seven Charts That Explain the New Normal for Oil Prices
  - Oil Futures Fall for Third Straight Week on Supply Outlook
  - U.S. Natural Gas Futures Rise With Support From LNG Exports
  - Oil Futures Post Weekly Losses on Rising Middle East Supply
  - Oil Falls Amid Risk-Off Sentiment
- Branch off “The Seven Charts That Explain the New Normal for Oil Prices”:
  - The close ties between Nvidia and Anthropic.
- Branch off “The Seven Charts That Explain the New Normal for Oil Prices”:
  - Auto & Transport Roundup: Market Talk
- Branch off “The Seven Charts That Explain the New Normal for Oil Prices”:
  - Data Centers Are the Growth Engine of America’s Power Grid
- Branch off “U.S. Natural Gas Futures Rise With Support From LNG Exports”:
  - Elon Musk on His Politics, a Potential Merger and Ukraine
- Branch off “Oil Falls Amid Risk-Off Sentiment”:
  - Built to Whisper, E.V.s Look to Mimic the Growl of Gas Engines
- Related: none

**8. Fed & interest rates** (markets, fixed, 10 items, 4 branches)
- Spine:
  - WSJ Dollar Index Rises 0.22% to 98.64
  - German Bund Yields Rise, French Yields Fall Ahead of PMI Data
  - U.S., European Bond Yields Rise, Reversing Last Week’s Sharp Falls
- Branch off “WSJ Dollar Index Rises 0.22% to 98.64”:
  - Fed Chairman Highlights Economic Uncertainty of A.I. Boom
  - Zohran Mamdani on Trump, Wall Street and Wealth Taxes
- Branch off “WSJ Dollar Index Rises 0.22% to 98.64”:
  - Debt Problems of the Richest Countries Are Trickling Down to the Poorest
  - The U.S. Could Hit Its Debt Limit by February
- Branch off “WSJ Dollar Index Rises 0.22% to 98.64”:
  - Facing Criticism, Trump Administration Says It’s Investigating Megaspeed
  - California Attorney General Issues Investigative Subpoena to Nvidia
- Branch off “WSJ Dollar Index Rises 0.22% to 98.64”:
  - Minutes of the Federal Open Market Committee, October 27-28, 2026
- Related: China · Nvidia · Xi · Scandal (world-news, 0.81); BOE’s Bailey Sees Length of Iran War as Key to Rate Path (world-news, 0.81)

**9. China · Nvidia · Xi · Scandal** (world-news, story, 10 items, 5 branches)
- Spine:
  - As Trump and Xi meet, China's AI dreams face an unexpected hurdle: the Nvidia spy scandal
  - Opinion / Chips Aren’t a Magic Bullet for China Risks
  - Giving Howard Lutnick His Due: China Is a Hard Problem
  - China’s Spies Set Sights on A.I. Chips Years Before Nvidia Scandal
- Branch off “As Trump and Xi meet, China's AI dreams face an unexpected h”:
  - Alice Huang’s Husband Built a Data-Center Empire Backed by the Chinese State
- Branch off “As Trump and Xi meet, China's AI dreams face an unexpected h”:
  - Why Neither Trump Nor Xi Is Likely to Raise Nvidia at Their Summit
  - American State Capitalism Helped Produce the Nvidia Scandal
- Branch off “As Trump and Xi meet, China's AI dreams face an unexpected h”:
  - In Choosing Shenzhen for Trump-Putin Summit, Xi Shows Off His Tech Ambitions
- Branch off “As Trump and Xi meet, China's AI dreams face an unexpected h”:
  - The Jensen Huang Saga Has Reinvigorated Washington’s China Hawks
- Branch off “China’s Spies Set Sights on A.I. Chips Years Before Nvidia S”:
  - A New Figure Emerges in the Nvidia Chip-Smuggling Saga
- Related: What’s So Important About Nvidia’s Chips? (us-politics, 0.92); Jensen · Alice · Huang · Nvidia (us-politics, 0.91); Trump threatens ‘tremendous tax’ for moving AI data centers outside the US (ai-news, 0.86); Information Technology (markets, 0.86); Financials (markets, 0.85)

**10. Health Care** (markets, fixed, 9 items, 4 branches)
- Spine:
  - When will Anthropic shares start trading?
  - What to Know About Anthropic’s Record-Breaking IPO
  - Anthropic Lives Up to Wall Street Hype, but AI Doubts Linger
  - Should You Invest in Anthropic? Here’s What to Consider.
  - Anthropic Committed to Spend $900 Billion. Wall Street Expects Its Debt to Be Junk.
- Branch off “Anthropic Lives Up to Wall Street Hype, but AI Doubts Linger”:
  - Judge Allows Trump’s Case Against The Times to Proceed
- Branch off “Should You Invest in Anthropic? Here’s What to Consider.”:
  - Health Care Roundup: Market Talk
- Branch off “Should You Invest in Anthropic? Here’s What to Consider.”:
  - Judge Approves $7 Billion Settlement Over Claims That Roundup Caused Cancer
- Branch off “Anthropic Committed to Spend $900 Billion. Wall Street Expec”:
  - Procter & Gamble to Increase Factory Shifts Without Humans to Cut Costs
- Related: Anthropic · IPO · Future · AI (us-politics, 0.91); Anthropic · Initial · Public · Offering (ai-news, 0.86)

**11. Anthropic · IPO · Future · AI** (us-politics, story, 9 items, 2 branches)
- Spine:
  - Congrats on Your Anthropic Shares
  - What the Anthropic IPO Means for the AI Future
  - The Astonishing Wealth of Anthropic
  - Anthropic's IPO caps an explosive growth period for the AI startup, filled with contradictions
  - EXCLUSIVE: Like SpaceX, Anthropic ran an unusual IPO process, chafing some bankers - Reuters
  - Anthropic's record IPO raises hopes for a charitable windfall that has nonprofits preparing to
  - WSJ Opinion: Anthropic’s Record-Breaking IPO
- Branch off “What the Anthropic IPO Means for the AI Future”:
  - Don’t Play Anthropic’s Game
- Branch off “The Astonishing Wealth of Anthropic”:
  - The Anthropic I.P.O. Will Change the Future of A.I.
- Related: Information Technology (markets, 0.93); Health Care (markets, 0.91); Anthropic · Initial · Public · Offering (ai-news, 0.87); Real Estate (markets, 0.85); Inflation & jobs reports (markets, 0.81)

**12. Headphones & earbuds** (tech-trackers, tracker, 9 items, 3 branches)
- Spine:
  - AirPods Pro 3 keep getting better, here’s what’s new in iOS 27
  - Official 2026 Amazon Black Friday sale now live! Millions of deals: Apple, Google, TVs, home, m
  - iOS 27 gave AirPods Pro a convenient new setting, here’s how to use it
  - Best Apple Black Friday deals now live: AirPods, MacBook Neo, Series 12, M6 MacBook Pro, more [
  - Beats Black Friday deals: $100 off new Beats 360, Powerbeats, more up to 53% off
- Branch off “Official 2026 Amazon Black Friday sale now live! Millions of”:
  - Nothing Headphone (1) Pro Headphones Review
- Branch off “Best Apple Black Friday deals now live: AirPods, MacBook Neo”:
  - $400 gaming headset Audeze Maxwell 2 ANC review: With planar drivers, premium technology, and A
  - Razer Hammerhead V3 X HyperSpeed Headphones Review
- Branch off “Best Apple Black Friday deals now live: AirPods, MacBook Neo”:
  - Your questions about Apple HomeView’s audio, answered
- Related: none

**13. Deal · Climate · Talks · COP31** (world-news, story, 7 items, 0 branches)
- Spine:
  - UN climate talk negotiators go into second day of overtime while at odds over fossil fuels
  - New draft deal aims to avert collapse of talks at COP31 climate summit
  - Why the failure to reach a major deal at UN climate talks matters as extreme weather worsens
  - COP31 fails to reach major climate deal as talks expose deep divisions
  - What's next after no deal at COP31 climate talks?
  - Analysis: The collapse of UN climate talks, over fossil fuels, was years in the making
  - Five takeaways from the failed climate talks COP31
- Related: U.N · Climate · Talks · Fossil (world-news, 0.85); Inside COP31: Part Trade Show, Part Climate Therapy Session (world-news, 0.84)

**14. Laptops** (tech-trackers, tracker, 7 items, 1 branches)
- Spine:
  - Acer Nitro V 16S AI (2025) Laptop Review
  - Acer Googlebook 14 (2026) Laptop Review
  - Dell XPS Googlebook 13 (2026) Laptop Review
  - XMG Neo 16 (M26) review: One of the best gaming laptops finally gets G-Sync
- Branch off “Acer Googlebook 14 (2026) Laptop Review”:
  - OLED iMac plans may be cancelled by Apple for two reasons
  - MacBook Pro PROLED, MacBook Neo, more: The best Amazon Black Friday deals on Macs
  - MacBook Neo 2 likely to launch around March, could feature new colors: report
- Related: none

**15. Inflation & jobs reports** (markets, fixed, 6 items, 0 branches)
- Spine:
  - What to know about the Nvidia turmoil.
  - Google Buys Worker Data From Spirit Airlines in a New Market to Feed A.I.
  - From Gig Workers to Tycoons, China Is Reaching Into Every Pocket
  - How the U.S. Economy Is Tied to A.I.
  - Agriculture Secretary Declares U.S. Cattle Supply Safe as Screwworm Cases Rise
  - Singapore's core inflation rate rises to 1.5% in October, below forecast
- Related: China · Nvidia · Xi · Scandal (world-news, 0.85); Anthropic · IPO · Future · AI (us-politics, 0.81)

**16. Materials** (markets, fixed, 5 items, 3 branches)
- Spine:
  - Gold, Silver Drop to Lowest Levels in Over a Year
  - Gold Rises in Likely Technical Rebound
- Branch off “Gold, Silver Drop to Lowest Levels in Over a Year”:
  - Basic Materials Roundup: Market Talk
- Branch off “Gold, Silver Drop to Lowest Levels in Over a Year”:
  - Grabbing Inflation Protection Now Is a No-Brainer
- Branch off “Gold Rises in Likely Technical Rebound”:
  - The Used Car Industry Is Booming. This N.J. Campus Is Setting the Price.
- Related: none

**17. Real Estate** (markets, fixed, 5 items, 3 branches)
- Spine:
  - How Anthropic sold itself to investors ahead of its I.P.O.
  - How Much Anthropic Are You About to Own?
- Branch off “How Much Anthropic Are You About to Own?”:
  - Why Big Investors Are Burning Lenders on Apartment Loans
- Branch off “How Much Anthropic Are You About to Own?”:
  - These Charts Show How More People Are Pulling Cash Out of Their Homes
- Branch off “How Anthropic sold itself to investors ahead of its I.P.O.”:
  - Nasdaq Turns Red For The Year
- Related: Anthropic · IPO · Future · AI (us-politics, 0.85); A 10% drop for the stock market is unnerving, but it's not that unusual (us-politics, 0.81); Anthropic · Initial · Public · Offering (ai-news, 0.81)

**18. Britain · Brexit** (world-news, story, 5 items, 1 branches)
- Spine:
  - The EU that Burnham is eyeing up is very different to the one Britain left
  - After Brexit, Britain’s Government Floats ‘Breturn’
  - Britain Announces Brexit Reset Deal at E.U. Summit: What to Know
  - Britain and Brussels Have Begun a Brexit Rollback. How Far Will It Go?
- Branch off “The EU that Burnham is eyeing up is very different to the on”:
  - Europe Games Out a Post-Trump World
- Related: UK-EU · Deal · Mean (world-news, 0.83)

**19. Myanmar · Genocide · Ruling · Court** (world-news, story, 6 items, 0 branches)
- Spine:
  - Bowen: Myanmar genocide verdict is historic and could have far-reaching implications
  - Myanmar Genocide Ruling Sets Up Court Fight Over Israel and Gaza
  - Myanmar Committed Genocide Against the Rohingya, Top Global Court Finds
  - How the Myanmar Genocide Ruling Raises the Stakes for Israel
  - Opinion / Defining Genocide Down at the International Court of Justice
  - A Landmark Genocide Ruling
- Related: Can a Country Be Guilty of Genocide? Finally, the Answer Is Yes. (us-politics, 0.90)

**20. Drug · Top · Mexico · Captured** (world-news, story, 5 items, 0 branches)
- Spine:
  - Cartel leader captured in northern Mexico in a bloody firefight that left 11 dead
  - Mexico Captures Top Drug Boss in Fierce Gunfight
  - Top Drug Kingpin Is Captured by Mexican Army as Gunfire Erupts
  - Drones, Texts and Diversions: How Mexico Captured a Most Wanted Man
  - Drug Kingpin’s Capture in Mexico Risks Bloody Succession Battle
- Related: none

## Follow-up (after review): fold one-item branches in tracker / fixed threads

- **The change:** new config `min_branch_items: 1` (story threads unchanged) and `min_branch_items_predefined: 2` (tracker / fixed). Storylines below the minimum fold into the spine (time order) and can anchor branches.
- **Real data:** branches 73 → 40. All 21 remaining one-item branches are in story threads. Tracker / fixed threads keep only multi-item side stories: Phones 6 → 2, Information Technology 3 → 1, Financials 8 → 2, Energy / Health Care / Materials → 0.
- **Tests:** pytest 476 (new folding test); validator OK.
