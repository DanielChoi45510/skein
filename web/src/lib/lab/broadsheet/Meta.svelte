<script lang="ts">
	// Byline: source in small caps, then plain-text labels. No pills.
	import type { ExportItem } from '$lib/types';
	import { fullDate, relativeTime } from '$lib/time';
	import { itemMeta, type LabCtx } from '../model';

	let { item, ctx, isNew = false }: { item: ExportItem; ctx: LabCtx; isNew?: boolean } = $props();
	const m = $derived(itemMeta(item, ctx.sources));
</script>

<p class="meta">
	{#if isNew}<span class="new">New</span>{/if}
	<span class="source">{m.source}</span>
	<time datetime={item.published_at} title={fullDate(item.published_at)}
		>{relativeTime(item.published_at, ctx.now)}</time
	>
	{#if m.kind}<span class="label">{m.kind}</span>{/if}
	{#if m.lean}<span class="label" title="Outlet's political lean (AllSides)">{m.lean}</span>{/if}
	{#if m.paywall}<span class="label" title={m.paywall}
			><span aria-hidden="true">🔒</span><span class="visually-hidden">{m.paywall}</span></span
		>{/if}
	{#if m.trial}<span class="label">Trial source</span>{/if}
</p>
{#if m.also.length}<p class="also">Also covered by {m.also.join(', ')}</p>{/if}

<style>
	.meta {
		display: flex;
		flex-wrap: wrap;
		gap: 0 0.55rem;
		margin: 0.35rem 0 0;
		font-size: 0.78rem;
		color: var(--ink-2);
	}
	.meta > * + *::before {
		content: '·';
		margin-right: 0.55rem;
	}
	.source {
		font-variant: small-caps;
		font-weight: 600;
		letter-spacing: 0.04em;
		color: var(--ink);
	}
	.label {
		font-style: italic;
	}
	.new {
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		font-size: 0.7rem;
		color: var(--red);
	}
	.also {
		margin: 0.2rem 0 0;
		font-size: 0.75rem;
		font-style: italic;
		color: var(--ink-2);
	}
</style>
