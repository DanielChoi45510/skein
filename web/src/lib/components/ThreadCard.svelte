<script lang="ts">
	import type { SourceSummary, ThreadSummary } from '$lib/types';
	import { fullDate, relativeTime } from '$lib/time';

	interface Props {
		thread: ThreadSummary;
		sources: Map<string, SourceSummary>;
		href: string;
		fresh: number; // new items since the last visit
		now: number;
	}
	let { thread, sources, href, fresh, now }: Props = $props();

	const latest = $derived(thread.latest);
	const latestSource = $derived(sources.get(latest.source_id)?.name ?? latest.source_id);
	// A one-item thread is titled with its headline; don't print it twice.
	const repeatsTitle = $derived(latest.title === thread.title);
	// Cooling threads sit under a "Quiet lately" heading; dormant ones are only grayed.
	const stateLabel = $derived(thread.state === 'dormant' ? 'Dormant' : null);
</script>

<article class:dormant={thread.state === 'dormant'} class:new={fresh > 0}>
	<h3><a {href}>{thread.title}</a></h3>
	<p class="meta">
		<span>{thread.item_count} {thread.item_count === 1 ? 'update' : 'updates'}</span>
		<span aria-hidden="true">·</span>
		<time datetime={thread.last_item_at} title={fullDate(thread.last_item_at)}>
			{relativeTime(thread.last_item_at, now)}
		</time>
		{#if fresh > 0}<span class="badge badge-new">{fresh} new</span>{/if}
		{#if stateLabel}<span class="badge">{stateLabel}</span>{/if}
	</p>
	<!-- Link out, never embed (CLAUDE.md principle 3). -->
	<a class="latest" href={latest.url} target="_blank" rel="noopener noreferrer">
		{#if repeatsTitle}
			<span class="source">Read at {latestSource}</span>
		{:else}
			<span class="visually-hidden">Latest:</span>
			{latest.title} <span class="source">— {latestSource}</span>
		{/if}
	</a>
</article>

<style>
	article {
		padding: 0.85rem 1rem;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: var(--radius);
	}
	article.new {
		border-left: 4px solid var(--new);
	}
	article.dormant {
		opacity: 0.65;
	}
	h3 {
		margin: 0;
		font-size: 1.1rem;
		line-height: 1.35;
		font-weight: 700;
	}
	h3 a {
		display: block;
		min-height: 44px;
		padding: 0.1rem 0;
		text-decoration: none;
	}
	h3 a:hover {
		text-decoration: underline;
	}
	.meta {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.35rem 0.5rem;
		margin: 0.1rem 0 0;
		font-size: 0.85rem;
		color: var(--muted);
	}
	.badge {
		padding: 0.05rem 0.45rem;
		border: 1px solid var(--border);
		border-radius: 999px;
		font-size: 0.75rem;
		line-height: 1.4;
	}
	.badge-new {
		border-color: var(--new);
		color: var(--new);
	}
	.latest {
		display: block;
		min-height: 44px;
		padding-top: 0.5rem;
		font-size: 0.95rem;
		text-decoration: none;
	}
	.latest:hover {
		text-decoration: underline;
	}
	.latest:visited {
		color: var(--muted);
	}
	.source {
		color: var(--muted);
		font-size: 0.85rem;
	}
</style>
