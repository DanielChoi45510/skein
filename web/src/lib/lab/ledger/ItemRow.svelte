<script lang="ts">
	// One story as a dense row: time, optional square thumb, condensed headline,
	// key:value meta. The headline links out.
	import type { ExportItem } from '$lib/types';
	import { fullDate } from '$lib/time';
	import { age, itemMeta, type LabCtx } from '../model';
	import { thumb } from '../thumb';

	let { item, ctx, isNew = false }: { item: ExportItem; ctx: LabCtx; isNew?: boolean } = $props();
	const m = $derived(itemMeta(item, ctx.sources));
	const img = $derived(thumb(item.id, 'pixel'));
</script>

<div class="row" class:new={isNew}>
	<time datetime={item.published_at} title={fullDate(item.published_at)}
		>{age(item.published_at, ctx.now)}</time
	>
	<div class="thumb">{#if img}<img src={img} alt="" width="8" height="8" loading="lazy" />{/if}</div>
	<div class="main">
		<a class="title" href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</a>
		{#if item.excerpt}<p class="ex">{item.excerpt}</p>{/if}
		<p class="kv">
			{#if isNew}<span class="flag">NEW</span>{/if}
			<span><i>src</i> {m.source}</span>
			{#if m.kind}<span><i>kind</i> {m.kind.toLowerCase()}</span>{/if}
			{#if m.lean}<span><i>lean</i> {m.lean.toLowerCase()}</span>{/if}
			{#if m.paywall}<span title={m.paywall}><i>pay</i> {m.paywall.toLowerCase()}</span>{/if}
			{#if m.trial}<span><i>status</i> trial</span>{/if}
			{#if m.also.length}<span><i>+also</i> {m.also.length}</span>{/if}
		</p>
	</div>
</div>

<style>
	.row {
		display: grid;
		grid-template-columns: 2.5rem 2.75rem minmax(0, 1fr);
		gap: 0.6rem;
		padding: 0.55rem 0;
	}
	time {
		padding-top: 0.15rem;
		font-size: 0.78rem;
		text-align: right;
		color: var(--dim);
		font-variant-numeric: tabular-nums;
	}
	.new time {
		color: var(--amber);
	}
	.thumb img {
		display: block;
		width: 2.75rem;
		height: 2.75rem;
		image-rendering: pixelated;
	}
	.title {
		display: block;
		font-family: var(--cond);
		font-stretch: condensed;
		font-size: 1.08rem;
		font-weight: 600;
		line-height: 1.25;
		text-decoration: none;
	}
	.title:hover {
		color: var(--teal);
		text-decoration: underline;
	}
	.title:visited {
		color: var(--dim);
	}
	.ex {
		display: -webkit-box;
		margin: 0.15rem 0 0;
		overflow: hidden;
		-webkit-line-clamp: 1;
		line-clamp: 1;
		-webkit-box-orient: vertical;
		font-size: 0.78rem;
		color: var(--dim);
	}
	.kv {
		display: flex;
		flex-wrap: wrap;
		gap: 0 0.9rem;
		margin: 0.2rem 0 0;
		font-size: 0.72rem;
	}
	.kv i {
		font-style: normal;
		color: var(--dim);
	}
	.kv i::after {
		content: ':';
	}
	.flag {
		color: var(--amber);
		font-weight: 700;
	}
</style>
