<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import DayList from '$lib/components/DayList.svelte';
	import { FeedError, fetchIndex, fetchThread } from '$lib/feed';
	import { groupByLocalDay } from '$lib/group';
	import { poll } from '$lib/poll';
	import type { FeedIndex, ThreadFeed } from '$lib/types';

	// The thread comes from ?id= so one prerendered page serves every thread.
	const id = $derived(page.url.searchParams.get('id') ?? '');

	let thread = $state<ThreadFeed | null>(null);
	let index = $state<FeedIndex | null>(null);
	let error = $state<string | null>(null);
	let now = $state(Date.now());

	async function load() {
		if (!id) {
			error = 'No thread selected.';
			return;
		}
		try {
			const [idx, t] = await Promise.all([fetchIndex(), fetchThread(id)]);
			index = idx;
			thread = t;
			error = null;
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
		load();
		return poll(load);
	});

	const sources = $derived(new Map((index?.sources ?? []).map((s) => [s.id, s])));
	const topicName = $derived(
		index?.groups.flatMap((g) => g.topics).find((t) => t.id === thread?.topic_id)?.name
	);
	const days = $derived(thread ? groupByLocalDay(thread.days) : []);
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
	<DayList {days} {sources} isNew={() => false} {now} />
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
	.error {
		margin: 1rem 0;
		padding: 0.75rem 1rem;
		border: 1px solid var(--accent);
		border-radius: var(--radius);
	}
</style>
