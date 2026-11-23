<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import { FeedError, fetchIndex, fetchTopic } from '$lib/feed';
	import { poll } from '$lib/poll';
	import { loadLastSeen, topicNewCount } from '$lib/readState';
	import { readStateReady } from '$lib/sync.svelte';
	import { relativeTime } from '$lib/time';
	import type { FeedIndex, TopicSummary } from '$lib/types';

	let index = $state<FeedIndex | null>(null);
	let counts = $state<Record<string, number>>({});
	let error = $state<string | null>(null);
	let now = $state(Date.now());

	async function load() {
		try {
			const [idx] = await Promise.all([fetchIndex(), readStateReady()]);
			const seen = loadLastSeen();
			const next: Record<string, number> = {};
			const toFetch: TopicSummary[] = [];
			for (const t of idx.groups.flatMap((g) => g.topics)) {
				const last = seen[t.id];
				const latest = t.latest_first_seen_at;
				if (!latest || (last && Date.parse(latest) <= Date.parse(last))) next[t.id] = 0;
				else toFetch.push(t);
			}
			const feeds = await Promise.all(toFetch.map((t) => fetchTopic(t.id).catch(() => null)));
			toFetch.forEach((t, i) => {
				const feed = feeds[i];
				next[t.id] = feed ? topicNewCount(feed, seen[t.id]) : 0;
			});
			index = idx;
			counts = next;
			error = null;
		} catch (e) {
			error = e instanceof FeedError ? e.message : 'Something went wrong loading the feed.';
		}
		now = Date.now();
	}

	onMount(() => {
		load();
		return poll(load);
	});

	const totalNew = $derived(Object.values(counts).reduce((a, b) => a + b, 0));
	const topicHref = (id: string) => `${resolve('/topic/')}?id=${encodeURIComponent(id)}`;
</script>

<h1 class="visually-hidden">Topics</h1>

{#if error}<p class="error" role="alert">{error}</p>{/if}

{#if index}
	{#each index.groups as group (group.id)}
		{@const active = group.topics.filter((t) => t.has_sources)}
		{@const idle = group.topics.filter((t) => !t.has_sources)}
		<section aria-labelledby="group-{group.id}">
			<h2 id="group-{group.id}">{group.name}</h2>
			{#if active.length}
				<ul>
					{#each active as topic (topic.id)}
						{@const n = counts[topic.id] ?? 0}
						<li>
							<a href={topicHref(topic.id)}>
								<span class="name">{topic.name}</span>
								{#if n > 0}
									<span class="count">{n} new</span>
								{:else if topic.visible_count === 0}
									<span class="muted">Nothing yet</span>
								{:else}
									<span class="muted">Up to date</span>
								{/if}
							</a>
						</li>
					{/each}
				</ul>
			{/if}
			{#if idle.length}
				<p class="idle muted">No sources yet: {idle.map((t) => t.name).join(', ')}</p>
			{/if}
		</section>
	{/each}

	<p class="caught-up">{totalNew > 0 ? "That's everything." : "You're all caught up."}</p>
	<p class="updated muted">
		Feed updated <time datetime={index.generated_at}>{relativeTime(index.generated_at, now)}</time>
	</p>
{:else if !error}
	<p class="muted">Loading…</p>
{/if}

<style>
	section {
		margin-top: 1.5rem;
	}
	h2 {
		margin: 0 0 0.5rem;
		font-size: 0.85rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--muted);
	}
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
		border: 1px solid var(--border);
		border-radius: var(--radius);
		background: var(--surface);
		overflow: hidden;
	}
	li + li {
		border-top: 1px solid var(--border);
	}
	li a {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		min-height: 52px;
		padding: 0.6rem 1rem;
		text-decoration: none;
	}
	li a:hover .name {
		text-decoration: underline;
	}
	.name {
		font-weight: 600;
	}
	.count {
		padding: 0.1rem 0.6rem;
		border-radius: 999px;
		background: var(--accent);
		color: var(--accent-text);
		font-size: 0.85rem;
		font-weight: 700;
		white-space: nowrap;
	}
	.idle {
		margin: 0.5rem 0 0;
		font-size: 0.85rem;
	}
	.updated {
		margin: -2rem 0 2rem;
		text-align: center;
		font-size: 0.8rem;
	}
	.error {
		margin: 1rem 0;
		padding: 0.75rem 1rem;
		border: 1px solid var(--accent);
		border-radius: var(--radius);
	}
</style>
