<script lang="ts">
	import type { ExportItem } from '$lib/types';
	import { fullDate, relativeTime } from '$lib/time';
	import { itemMeta, type LabCtx } from '../model';
	import { thumb } from '../thumb';

	let { item, ctx, isNew = false }: { item: ExportItem; ctx: LabCtx; isNew?: boolean } = $props();
	const m = $derived(itemMeta(item, ctx.sources));
	const img = $derived(thumb(item.id, 'blob'));
</script>

<article>
	{#if img}<img src={img} alt="" width="160" height="120" loading="lazy" />{/if}
	<div class="body">
		<p class="chips">
			{#if isNew}<span class="chip new">New</span>{/if}
			<span class="chip">{m.source}</span>
			{#if m.kind}<span class="chip">{m.kind}</span>{/if}
			{#if m.lean}<span class="chip" title="Outlet's political lean (AllSides)">{m.lean}</span>{/if}
			{#if m.paywall}<span class="chip" title={m.paywall}
					><span aria-hidden="true">🔒</span><span class="visually-hidden">{m.paywall}</span></span
				>{/if}
			{#if m.trial}<span class="chip">Trial</span>{/if}
		</p>
		<h3><a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</a></h3>
		{#if item.excerpt}<p class="ex">{item.excerpt}</p>{/if}
		<p class="foot">
			<time datetime={item.published_at} title={fullDate(item.published_at)}
				>{relativeTime(item.published_at, ctx.now)}</time
			>
			{#if m.also.length}· also in {m.also.join(', ')}{/if}
		</p>
	</div>
</article>

<style>
	article {
		overflow: hidden;
		border-radius: 22px;
		background: var(--surface);
		box-shadow: var(--shadow);
	}
	img {
		display: block;
		width: calc(100% - 1rem);
		height: auto;
		aspect-ratio: 4 / 3;
		margin: 0.5rem 0.5rem 0;
		border-radius: 16px;
		object-fit: cover;
		filter: var(--img-filter);
	}
	.body {
		padding: 0.85rem 1.1rem 1rem;
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
		margin: 0;
	}
	.chip {
		padding: 0.1rem 0.55rem;
		border-radius: 999px;
		background: var(--chip);
		font-size: 0.72rem;
		font-weight: 600;
		color: var(--dim);
	}
	.chip.new {
		background: hsl(var(--h) var(--pop-s) var(--pop-l));
		color: var(--bg);
	}
	h3 {
		margin: 0.5rem 0 0;
		font-size: 1.12rem;
		font-weight: 700;
		line-height: 1.3;
	}
	h3 a {
		display: block;
		min-height: 44px;
		text-decoration: none;
	}
	h3 a:hover {
		text-decoration: underline;
		text-decoration-thickness: 2px;
		text-decoration-color: hsl(var(--h) var(--pop-s) var(--pop-l));
	}
	.ex {
		display: -webkit-box;
		margin: 0.2rem 0 0;
		overflow: hidden;
		-webkit-line-clamp: 3;
		line-clamp: 3;
		-webkit-box-orient: vertical;
		font-size: 0.92rem;
		color: var(--dim);
	}
	.foot {
		margin: 0.6rem 0 0;
		font-size: 0.78rem;
		color: var(--dim);
	}
</style>
