<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import ItemCard from '$lib/components/ItemCard.svelte';
	import { FeedError, fetchIndex, fetchTopic } from '$lib/feed';
	import { allItems, groupByLocalDay } from '$lib/group';
	import { poll } from '$lib/poll';
	import { isNew, latestFirstSeen, loadLastSeen, markSeen, newCount } from '$lib/readState';
	import { dayLabel } from '$lib/time';
	import type { FeedIndex, TopicFeed } from '$lib/types';

	// The topic comes from ?id= so one prerendered page serves every topic.
	const id = $derived(page.url.searchParams.get('id') ?? '');

	let feed = $state<TopicFeed | null>(null);
	let index = $state<FeedIndex | null>(null);
	let error = $state<string | null>(null);
	let now = $state(Date.now());
	// "Last visit" is read once, before this visit marks the topic as seen.
	let previousVisit = $state<string | undefined>(undefined);
	let firstLoad = true;
	let expanded = $state<Record<string, boolean>>({});

	async function load() {
		if (!id) {
			error = 'No topic selected.';
			return;
		}
		try {
			const [idx, topic] = await Promise.all([fetchIndex(), fetchTopic(id)]);
			if (firstLoad) {
				previousVisit = loadLastSeen()[id];
				firstLoad = false;
			}
			index = idx;
			feed = topic;
			error = null;
			const latest = latestFirstSeen(allItems(topic.days));
			if (latest) markSeen(id, latest);
		} catch (e) {
			if (e instanceof FeedError && e.message === 'Not found.') error = "This topic doesn't exist.";
			else error = e instanceof FeedError ? e.message : 'Something went wrong loading the topic.';
		}
		now = Date.now();
	}

	onMount(() => {
		load();
		return poll(load);
	});

	const sources = $derived(new Map((index?.sources ?? []).map((s) => [s.id, s])));
	const days = $derived(feed ? groupByLocalDay(feed.days) : []);
	const fresh = $derived(feed ? newCount(allItems(feed.days), previousVisit) : 0);
	// No "New" badges on a first visit: there's nothing to compare against.
	const showNew = (item: Parameters<typeof isNew>[0]) =>
		previousVisit !== undefined && isNew(item, previousVisit);
</script>

<svelte:head>
	<title>{feed ? `${feed.name} · Skein` : 'Skein'}</title>
</svelte:head>

<nav><a href={resolve('/')}>← All topics</a></nav>

{#if error}<p class="error" role="alert">{error}</p>{/if}

{#if feed}
	<h1>{feed.name}</h1>
	<p class="summary muted">
		{#if previousVisit === undefined}
			First visit
		{:else if fresh > 0}
			{fresh} new since your last visit
		{:else}
			Nothing new since your last visit
		{/if}
	</p>

	{#each days as day (day.key)}
		<section aria-labelledby="day-{day.key}">
			<h2 id="day-{day.key}">{dayLabel(day.key, now)}</h2>
			<ul>
				{#each day.shown as item (item.id)}
					<li><ItemCard {item} {sources} isNew={showNew(item)} {now} /></li>
				{/each}
				{#if expanded[day.key]}
					{#each day.more as item (item.id)}
						<li><ItemCard {item} {sources} isNew={showNew(item)} {now} /></li>
					{/each}
				{/if}
			</ul>
			{#if day.more.length}
				<button
					type="button"
					class="more"
					aria-expanded={expanded[day.key] ?? false}
					onclick={() => (expanded[day.key] = !expanded[day.key])}
				>
					{expanded[day.key] ? 'Show fewer' : `+${day.more.length} more`}
				</button>
			{/if}
		</section>
	{:else}
		<p class="muted">Nothing here in the last few days.</p>
	{/each}

	<p class="caught-up">You're all caught up.</p>
{:else if !error}
	<p class="muted">Loading…</p>
{/if}

<style>
	nav a {
		display: inline-flex;
		align-items: center;
		min-height: 44px;
		color: var(--muted);
		text-decoration: none;
	}
	nav a:hover {
		text-decoration: underline;
	}
	h1 {
		margin: 0.25rem 0 0;
		font-size: 1.6rem;
		line-height: 1.2;
	}
	.summary {
		margin: 0.25rem 0 0;
	}
	section {
		margin-top: 1.75rem;
	}
	h2 {
		margin: 0 0 0.6rem;
		font-size: 0.85rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--muted);
	}
	ul {
		display: grid;
		gap: 0.6rem;
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.more {
		display: block;
		width: 100%;
		min-height: 44px;
		margin-top: 0.6rem;
		border: 1px dashed var(--border);
		border-radius: var(--radius);
		background: transparent;
		color: var(--muted);
		cursor: pointer;
	}
	.more:hover {
		color: var(--text);
	}
	.error {
		margin: 1rem 0;
		padding: 0.75rem 1rem;
		border: 1px solid var(--accent);
		border-radius: var(--radius);
	}
</style>
