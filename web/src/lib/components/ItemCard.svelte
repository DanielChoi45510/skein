<script lang="ts">
	import type { ExportItem, SourceSummary } from '$lib/types';
	import { fullDate, relativeTime } from '$lib/time';
	import { kindLabel, leanLabel, paywallLabel } from '$lib/labels';

	interface Props {
		item: ExportItem;
		sources: Map<string, SourceSummary>;
		isNew: boolean;
		now: number;
		/** Owner selection (move / split); no checkbox unless given. */
		selected?: boolean;
		onToggle?: () => void;
	}
	let { item, sources, isNew, now, selected, onToggle }: Props = $props();

	const source = $derived(sources.get(item.source_id));
	const kind = $derived(kindLabel(source?.kind ?? null));
	const lean = $derived(leanLabel(source?.lean ?? null));
	const paywall = $derived(paywallLabel(source?.paywall));
	const also = $derived(item.also_covered_by.map((id) => sources.get(id)?.name ?? id));
</script>

<article class:new={isNew} class:selected>
	{#if onToggle}
		<label class="select">
			<input type="checkbox" checked={selected} onchange={onToggle} />
			<span class="visually-hidden">Select “{item.title}”</span>
		</label>
	{/if}
	<h3>
		<!-- Link out, never embed (CLAUDE.md principle 3). -->
		<a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</a>
	</h3>
	<p class="meta">
		<span class="source">{source?.name ?? item.source_id}</span>
		<span aria-hidden="true">·</span>
		<time datetime={item.published_at} title={fullDate(item.published_at)}>
			{relativeTime(item.published_at, now)}
		</time>
		{#if isNew}<span class="badge badge-new">New</span>{/if}
		{#if kind}<span class="badge">{kind}</span>{/if}
		{#if lean}<span class="badge" title="Outlet's political lean (AllSides)">{lean}</span>{/if}
		{#if paywall}<span class="badge" title={paywall}
				><span aria-hidden="true">🔒</span><span class="visually-hidden">{paywall}</span></span
			>{/if}
		{#if source?.status === 'trial'}<span class="badge badge-trial" title="Source on trial"
				>Trial</span
			>{/if}
	</p>
	{#if item.excerpt}<p class="excerpt">{item.excerpt}</p>{/if}
	{#if also.length}<p class="also">Also covered by {also.join(', ')}</p>{/if}
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
	article {
		position: relative;
	}
	article.selected {
		outline: 2px solid var(--accent);
	}
	.select {
		float: right;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 44px;
		min-height: 44px;
		margin: -0.5rem -0.6rem 0 0.25rem;
		cursor: pointer;
	}
	.select input {
		width: 1.2rem;
		height: 1.2rem;
		accent-color: var(--accent);
	}
	h3 {
		margin: 0;
		font-size: 1.05rem;
		line-height: 1.35;
		font-weight: 600;
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
	h3 a:visited {
		color: var(--muted);
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
	.source {
		font-weight: 600;
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
	.badge-trial {
		border-style: dashed;
	}
	.excerpt {
		margin: 0.5rem 0 0;
		font-size: 0.95rem;
	}
	.also {
		margin: 0.4rem 0 0;
		font-size: 0.8rem;
		color: var(--muted);
	}
</style>
