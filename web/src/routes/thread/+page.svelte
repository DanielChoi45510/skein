<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import DayList from '$lib/components/DayList.svelte';
	import { FeedError, fetchIndex, fetchThread } from '$lib/feed';
	import { allItems, groupByLocalDay, inTimeOrder, type Order } from '$lib/group';
	import { poll } from '$lib/poll';
	import { loadThreadOrder, saveThreadOrder } from '$lib/prefs';
	import { isNew, latestFirstSeen, loadThreadSeen, markThreadSeen, newCount } from '$lib/readState';
	import { relativeTime } from '$lib/time';
	import type { ExportItem, FeedIndex, ThreadFeed } from '$lib/types';

	// The thread comes from ?id= so one prerendered page serves every thread.
	const id = $derived(page.url.searchParams.get('id') ?? '');

	let thread = $state<ThreadFeed | null>(null);
	let index = $state<FeedIndex | null>(null);
	let error = $state<string | null>(null);
	let now = $state(Date.now());
	// "Last visit" is read once, before this visit marks the thread as seen. A thread
	// never opened starts from its topic's previous visit (seeded by the topic page).
	let previousVisit = $state<string | undefined>(undefined);
	let firstLoad = true;
	let order = $state<Order>('newest');

	async function load() {
		if (!id) {
			error = 'No thread selected.';
			return;
		}
		try {
			const [idx, t] = await Promise.all([fetchIndex(), fetchThread(id)]);
			if (firstLoad) {
				previousVisit = loadThreadSeen()[id];
				firstLoad = false;
			}
			index = idx;
			thread = t;
			error = null;
			const latest = latestFirstSeen(allItems(t.days));
			if (latest) markThreadSeen(id, latest);
		} catch (e) {
			if (e instanceof FeedError && e.message === 'Not found.') {
				error = 'This thread is no longer in the feed.';
			} else {
				error = e instanceof FeedError ? e.message : 'Something went wrong loading the thread.';
			}
		}
		now = Date.now();
	}

	onMount(() => {
		order = loadThreadOrder();
		load();
		return poll(load);
	});

	function setOrder(next: Order) {
		order = next;
		saveThreadOrder(next);
	}

	const sources = $derived(new Map((index?.sources ?? []).map((s) => [s.id, s])));
	const topicName = $derived(
		index?.groups.flatMap((g) => g.topics).find((t) => t.id === thread?.topic_id)?.name
	);
	const days = $derived(thread ? inTimeOrder(groupByLocalDay(thread.days), order) : []);
	const items = $derived(thread ? allItems(thread.days) : []);
	const fresh = $derived(newCount(items, previousVisit));
	// No "New" badges on a first visit: there's nothing to compare against.
	const showNew = (item: ExportItem) => previousVisit !== undefined && isNew(item, previousVisit);
	const topicHref = $derived(
		thread ? `${resolve('/topic/')}?id=${encodeURIComponent(thread.topic_id)}` : resolve('/')
	);
</script>

<svelte:head>
	<title>{thread ? `${thread.title} · Skein` : 'Skein'}</title>
</svelte:head>

<nav><a href={topicHref}>← {topicName ?? 'Back'}</a></nav>

{#if error}<p class="error" role="alert">{error}</p>{/if}

{#if thread}
	<h1>{thread.title}</h1>
	<p class="summary muted">
		{#if previousVisit === undefined}
			First visit · {items.length} {items.length === 1 ? 'update' : 'updates'}
		{:else if fresh > 0}
			{fresh} {fresh === 1 ? 'update' : 'updates'} since your last visit
			<time datetime={previousVisit}>({relativeTime(previousVisit, now)})</time>
		{:else}
			Nothing new since your last visit
		{/if}
	</p>

	<div class="order" role="group" aria-label="Order">
		<button type="button" aria-pressed={order === 'newest'} onclick={() => setOrder('newest')}>
			Newest first
		</button>
		<button
			type="button"
			aria-pressed={order === 'chronological'}
			onclick={() => setOrder('chronological')}
		>
			Oldest first
		</button>
	</div>

	<DayList {days} {sources} isNew={showNew} {now} />
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
	.order {
		display: inline-flex;
		margin-top: 1rem;
		border: 1px solid var(--border);
		border-radius: 999px;
		overflow: hidden;
	}
	.order button {
		min-height: 44px;
		padding: 0 1rem;
		border: 0;
		background: transparent;
		color: var(--muted);
		font-size: 0.9rem;
		cursor: pointer;
	}
	.order button + button {
		border-left: 1px solid var(--border);
	}
	.order button[aria-pressed='true'] {
		background: var(--surface);
		color: var(--text);
		font-weight: 600;
	}
	.error {
		margin: 1rem 0;
		padding: 0.75rem 1rem;
		border: 1px solid var(--accent);
		border-radius: var(--radius);
	}
</style>
