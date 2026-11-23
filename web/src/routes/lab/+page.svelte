<script lang="ts">
	// Design lab (UI overhaul step 1): three switchable visual directions over the
	// same feed, for comparing on phone and laptop. Not linked from the app, and
	// read-only: it never marks topics or threads as seen.
	import { onMount, type Component } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { FeedError, fetchIndex, fetchThread, fetchTopic } from '$lib/feed';
	import { loadLastSeen, safeStorage, type LastSeen } from '$lib/readState';
	import type { FeedIndex, ThreadFeed, TopicFeed } from '$lib/types';
	import { buildTiles, topicView, type DirectionProps, type LabCtx } from '$lib/lab/model';
	import { buildSpine, pickThread } from '$lib/lab/spine';
	import {
		DIRECTION_NAMES,
		DIRECTIONS,
		THEMES,
		VIEWS,
		hasStateParams,
		loadSaved,
		parseState,
		save,
		toQuery,
		type Direction,
		type LabState
	} from '$lib/lab/state';
	import Broadsheet from '$lib/lab/broadsheet/Root.svelte';
	import Ledger from '$lib/lab/ledger/Root.svelte';
	import Pebble from '$lib/lab/pebble/Root.svelte';

	const ROOTS: Record<Direction, Component<DirectionProps>> = {
		broadsheet: Broadsheet,
		ledger: Ledger,
		pebble: Pebble
	};

	const lab = $derived(parseState(page.url.searchParams));
	const href = (patch: Partial<LabState>) => `${resolve('/lab/')}${toQuery({ ...lab, ...patch })}`;

	let index = $state<FeedIndex | null>(null);
	let feeds = $state<Record<string, TopicFeed | null>>({});
	let thread = $state<ThreadFeed | null>(null);
	let lastSeen = $state<LastSeen>({});
	let error = $state<string | null>(null);
	const now = Date.now();

	onMount(() => {
		// A bare /lab/ reopens the last combination this browser looked at.
		if (!hasStateParams(page.url.searchParams)) {
			const saved = loadSaved(safeStorage());
			if (saved) goto(`${resolve('/lab/')}${saved}`, { replaceState: true, noScroll: true });
		}
		lastSeen = loadLastSeen();
		(async () => {
			try {
				const idx = await fetchIndex();
				const topics = idx.groups.flatMap((g) => g.topics);
				const loaded = await Promise.all(
					topics.map((t) => (t.has_sources ? fetchTopic(t.id).catch(() => null) : null))
				);
				feeds = Object.fromEntries(topics.map((t, i) => [t.id, loaded[i]]));
				index = idx;
			} catch (e) {
				error = e instanceof FeedError ? e.message : 'Something went wrong loading the feed.';
			}
		})();
	});

	$effect(() => save(safeStorage(), lab));

	const tiles = $derived(index ? buildTiles(index, feeds, lastSeen) : []);
	const topicId = $derived.by(() => {
		if (lab.topic && feeds[lab.topic]) return lab.topic;
		return [...tiles].sort((a, b) => b.weight - a.weight)[0]?.id ?? null;
	});
	const topic = $derived(topicId && feeds[topicId] ? topicView(feeds[topicId]) : null);
	const picked = $derived(
		index
			? pickThread(
					Object.values(feeds).filter((f): f is TopicFeed => f !== null),
					lab.topic,
					lab.thread
				)
			: null
	);

	$effect(() => {
		if (lab.v !== 'thread' || !picked || thread?.id === picked.threadId) return;
		const want = picked.threadId;
		fetchThread(want)
			.then((t) => {
				if (picked?.threadId === want) thread = t;
			})
			.catch(() => (error = "This thread couldn't be loaded."));
	});

	const spine = $derived(
		picked && thread?.id === picked.threadId ? buildSpine(thread, feeds[picked.topicId]) : null
	);

	const status = $derived.by(() => {
		if (error) return error;
		if (!index) return 'Loading…';
		if (lab.v === 'topic' && !topic) return 'No topic to show.';
		if (lab.v === 'thread' && !picked) return 'No threads in this feed yet.';
		if (lab.v === 'thread' && !spine) return 'Loading…';
		return null;
	});

	const ctx: LabCtx = $derived({
		sources: new Map((index?.sources ?? []).map((s) => [s.id, s])),
		now,
		lastSeen,
		href
	});

	const Root = $derived(ROOTS[lab.d]);
	const VIEW_NAMES = { home: 'Home', topic: 'Topic', thread: 'Thread' } as const;
	const THEME_NAMES = { auto: 'Auto', dark: 'Dark', light: 'Light' } as const;
</script>

<svelte:head>
	<title>Lab · {DIRECTION_NAMES[lab.d]} · Skein</title>
	<meta name="robots" content="noindex" />
</svelte:head>

<nav class="labbar" aria-label="Design lab">
	<span class="tag">Design lab</span>
	<div class="seg" role="group" aria-label="Direction">
		{#each DIRECTIONS as d, i (d)}
			<a href={href({ d })} aria-current={lab.d === d ? 'true' : undefined}
				><span class="letter">{'ABC'[i]}</span> {DIRECTION_NAMES[d]}</a
			>
		{/each}
	</div>
	<div class="seg" role="group" aria-label="View">
		{#each VIEWS as v (v)}
			<a href={href({ v })} aria-current={lab.v === v ? 'true' : undefined}>{VIEW_NAMES[v]}</a>
		{/each}
	</div>
	<div class="seg" role="group" aria-label="Theme">
		{#each THEMES as theme (theme)}
			<a href={href({ theme })} aria-current={lab.theme === theme ? 'true' : undefined}
				>{THEME_NAMES[theme]}</a
			>
		{/each}
	</div>
</nav>

<Root
	view={lab.v}
	theme={lab.theme}
	{tiles}
	generatedAt={index?.generated_at ?? null}
	{topic}
	{spine}
	{status}
	{ctx}
/>

<style>
	.labbar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.4rem 0.75rem;
		padding: max(0.4rem, env(safe-area-inset-top)) max(0.75rem, env(safe-area-inset-right)) 0.4rem
			max(0.75rem, env(safe-area-inset-left));
		background: #1c1d21;
		color: #e9e9ec;
		border-bottom: 1px solid #34363c;
		font:
			500 0.8rem/1.2 system-ui,
			-apple-system,
			sans-serif;
		color-scheme: dark;
		z-index: 10;
	}
	@media (min-width: 40rem) {
		.labbar {
			position: sticky;
			top: 0;
		}
	}
	@media (max-width: 39.99rem) {
		.tag {
			display: none;
		}
		.seg a {
			padding: 0 0.55rem;
		}
	}
	.tag {
		padding: 0.2rem 0.5rem;
		border: 1px dashed #6b6e78;
		border-radius: 4px;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		font-size: 0.68rem;
		color: #b9bbc3;
	}
	.seg {
		display: inline-flex;
		flex-wrap: wrap;
		padding: 2px;
		border-radius: 8px;
		background: #2a2c32;
	}
	.seg a {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		min-height: 44px;
		padding: 0 0.7rem;
		border-radius: 6px;
		color: #c9cbd2;
		text-decoration: none;
	}
	.seg a:hover {
		color: #fff;
	}
	.seg a[aria-current='true'] {
		background: #f1f1f3;
		color: #16171a;
	}
	.letter {
		display: inline-grid;
		place-items: center;
		width: 1.2rem;
		height: 1.2rem;
		border-radius: 50%;
		border: 1px solid currentColor;
		font-size: 0.65rem;
		font-weight: 700;
	}
</style>
