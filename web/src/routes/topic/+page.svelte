<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import DayList from '$lib/components/DayList.svelte';
	import ItemCard from '$lib/components/ItemCard.svelte';
	import ThreadCard from '$lib/components/ThreadCard.svelte';
	import TopicOwnerPanel from '$lib/components/TopicOwnerPanel.svelte';
	import { owner } from '$lib/owner.svelte';
	import { FeedError, fetchIndex, fetchTopic } from '$lib/feed';
	import { groupByLocalDay } from '$lib/group';
	import { poll } from '$lib/poll';
	import {
		isNew,
		loadLastSeen,
		loadThreadSeen,
		markSeen,
		newSince,
		seedThreadSeen,
		topicLatestFirstSeen,
		topicNewCount
	} from '$lib/readState';
	import { readStateReady } from '$lib/sync.svelte';
	import { isThreaded, topicLayout } from '$lib/topicView';
	import type { ExportItem, FeedIndex, ThreadSummary, TopicFeed } from '$lib/types';

	// The topic comes from ?id= so one prerendered page serves every topic.
	const id = $derived(page.url.searchParams.get('id') ?? '');

	let feed = $state<TopicFeed | null>(null);
	let index = $state<FeedIndex | null>(null);
	let error = $state<string | null>(null);
	let now = $state(Date.now());
	// "Last visit" is read once, before this visit marks the topic as seen.
	let previousVisit = $state<string | undefined>(undefined);
	let threadSeen = $state<Record<string, string>>({}); // read once, like previousVisit
	let firstLoad = true;
	let showMoreItems = $state(false);
	let showDormant = $state(false);
	// Owner: select single stories to move into a thread.
	let selecting = $state(false);
	let selected = $state<string[]>([]);
	const toggle = (itemId: string) =>
		(selected = selected.includes(itemId)
			? selected.filter((i) => i !== itemId)
			: [...selected, itemId]);
	const selectProps = (itemId: string) =>
		selecting
			? { selected: selected.includes(itemId), onToggle: () => toggle(itemId) }
			: {};

	async function load() {
		if (!id) {
			error = 'No topic selected.';
			return;
		}
		try {
			const [idx, topic] = await Promise.all([fetchIndex(), fetchTopic(id)]);
			if (firstLoad) {
				await readStateReady(); // the owner's synced read state, if any
				previousVisit = loadLastSeen()[id];
				threadSeen = loadThreadSeen();
				firstLoad = false;
			}
			index = idx;
			feed = topic;
			error = null;
			seedThreadSeen(
				topic.threads.map((t) => t.id),
				previousVisit
			);
			const latest = topicLatestFirstSeen(topic);
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
	const threaded = $derived(feed ? isThreaded(feed) : false);
	const layout = $derived(feed && threaded ? topicLayout(feed) : null);
	const days = $derived(feed && !threaded ? groupByLocalDay(feed.days) : []);
	const fresh = $derived(feed ? topicNewCount(feed, previousVisit) : 0);
	const empty = $derived(
		layout
			? !layout.pinned.length &&
				!layout.live.length &&
				!layout.cooling.length &&
				!layout.dormant.length
			: !days.length
	);
	// No "New" badges on a first visit: there's nothing to compare against.
	const showNew = (item: ExportItem) => previousVisit !== undefined && isNew(item, previousVisit);
	// A thread's own last visit, else the topic's (what seedThreadSeen stores for it).
	const threadFresh = (t: ThreadSummary) => {
		const since = threadSeen[t.id] ?? previousVisit;
		return since === undefined ? 0 : newSince(t.first_seen, since);
	};
	const threadHref = (threadId: string) =>
		`${resolve('/thread/')}?id=${encodeURIComponent(threadId)}`;
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

	{#if owner.signedIn && layout}
		<TopicOwnerPanel
			{feed}
			bind:selecting
			{selected}
			onClearSelection={() => {
				selected = [];
				selecting = false;
			}}
		/>
	{/if}

	{#if layout}
		{#if layout.pinned.length}
			<section aria-labelledby="pinned">
				<h2 id="pinned">Pinned</h2>
				<ul class="cards">
					{#each layout.pinned as thread (thread.id)}
						<li>
							<ThreadCard
								{thread}
								{sources}
								href={threadHref(thread.id)}
								fresh={threadFresh(thread)}
								{now}
							/>
						</li>
					{/each}
				</ul>
			</section>
		{/if}
		{#if layout.live.length}
			<ul class="cards">
				{#each layout.live as entry (entry.id)}
					<li>
						{#if entry.kind === 'thread'}
							<ThreadCard
								thread={entry.thread}
								{sources}
								href={threadHref(entry.thread.id)}
								fresh={threadFresh(entry.thread)}
								{now}
							/>
						{:else}
							<ItemCard
								item={entry.item}
								{sources}
								isNew={showNew(entry.item)}
								{now}
								{...selectProps(entry.item.id)}
							/>
						{/if}
					</li>
				{/each}
				{#if showMoreItems}
					{#each layout.moreItems as item (item.id)}
						<li>
							<ItemCard {item} {sources} isNew={showNew(item)} {now} {...selectProps(item.id)} />
						</li>
					{/each}
				{/if}
			</ul>
			{#if layout.moreItems.length}
				<button
					type="button"
					class="more"
					aria-expanded={showMoreItems}
					onclick={() => (showMoreItems = !showMoreItems)}
				>
					{showMoreItems ? 'Show fewer' : `+${layout.moreItems.length} more single stories`}
				</button>
			{/if}
		{/if}

		{#if layout.cooling.length}
			<section aria-labelledby="cooling">
				<h2 id="cooling">Quiet lately</h2>
				<ul class="cards">
					{#each layout.cooling as thread (thread.id)}
						<li>
							<ThreadCard
								{thread}
								{sources}
								href={threadHref(thread.id)}
								fresh={threadFresh(thread)}
								{now}
							/>
						</li>
					{/each}
				</ul>
			</section>
		{/if}

		{#if layout.dormant.length}
			<section aria-labelledby="dormant">
				<h2 id="dormant" class="visually-hidden">Dormant threads</h2>
				<button
					type="button"
					class="more"
					aria-expanded={showDormant}
					aria-controls="dormant-list"
					onclick={() => (showDormant = !showDormant)}
				>
					{showDormant
						? 'Hide dormant threads'
						: `Show ${layout.dormant.length} dormant ${layout.dormant.length === 1 ? 'thread' : 'threads'}`}
				</button>
				{#if showDormant}
					<ul class="cards" id="dormant-list">
						{#each layout.dormant as thread (thread.id)}
							<li>
								<ThreadCard
									{thread}
									{sources}
									href={threadHref(thread.id)}
									fresh={threadFresh(thread)}
									{now}
								/>
							</li>
						{/each}
					</ul>
				{/if}
			</section>
		{/if}
	{:else}
		<DayList {days} {sources} isNew={showNew} {now} />
	{/if}

	{#if empty}
		<p class="muted">Nothing here in the last few days.</p>
	{/if}

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
	.cards {
		display: grid;
		gap: 0.6rem;
		list-style: none;
		margin: 1.25rem 0 0;
		padding: 0;
	}
	section .cards {
		margin-top: 0;
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
