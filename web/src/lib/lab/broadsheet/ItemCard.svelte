<script lang="ts">
	import type { ExportItem } from '$lib/types';
	import { thumb } from '../thumb';
	import type { LabCtx } from '../model';
	import Meta from './Meta.svelte';

	interface Props {
		item: ExportItem;
		ctx: LabCtx;
		isNew?: boolean;
		lead?: boolean;
	}
	let { item, ctx, isNew = false, lead = false }: Props = $props();
	const img = $derived(thumb(item.id, 'duotone'));
</script>

<article class:lead class:has-img={!!img}>
	{#if img}<img src={img} alt="" width="160" height="90" loading="lazy" />{/if}
	<div class="body">
		<h3>
			<!-- Link out, never embed (CLAUDE.md principle 3). -->
			<a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</a>
		</h3>
		{#if item.excerpt}<p class="dek">{item.excerpt}</p>{/if}
		<Meta {item} {ctx} {isNew} />
	</div>
</article>

<style>
	article {
		display: grid;
		gap: 0.4rem 1rem;
	}
	article.has-img:not(.lead) {
		grid-template-columns: 1fr 6.5rem;
	}
	article.has-img:not(.lead) img {
		grid-column: 2;
		grid-row: 1;
		width: 6.5rem;
		aspect-ratio: 4 / 3;
	}
	img {
		display: block;
		width: 100%;
		height: auto;
		aspect-ratio: 16 / 9;
		object-fit: cover;
		filter: var(--img-filter);
	}
	.body {
		grid-row: 1;
		min-width: 0;
	}
	.lead .body {
		grid-row: auto;
	}
	h3 {
		margin: 0;
		font-family: var(--serif);
		font-size: 1.2rem;
		font-weight: 600;
		line-height: 1.25;
	}
	.lead h3 {
		font-size: clamp(1.6rem, 4vw, 2.3rem);
		font-weight: 700;
		line-height: 1.12;
		letter-spacing: -0.01em;
	}
	h3 a {
		text-decoration: none;
	}
	h3 a:hover {
		text-decoration: underline;
		text-decoration-thickness: 1px;
		text-underline-offset: 0.15em;
	}
	.dek {
		display: -webkit-box;
		margin: 0.35rem 0 0;
		overflow: hidden;
		-webkit-line-clamp: 3;
		line-clamp: 3;
		-webkit-box-orient: vertical;
		font-family: var(--serif);
		font-size: 0.98rem;
		color: var(--ink-2);
	}
	.lead .dek {
		-webkit-line-clamp: 5;
		line-clamp: 5;
		font-size: 1.1rem;
	}
</style>
