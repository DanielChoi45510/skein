<script lang="ts">
	import type { ThreadSummary } from '$lib/types';
	import { relativeTime } from '$lib/time';
	import { thumb } from '../thumb';
	import { itemMeta, type LabCtx } from '../model';

	interface Props {
		thread: ThreadSummary;
		ctx: LabCtx;
		topicId: string;
		fresh?: number;
		lead?: boolean;
	}
	let { thread, ctx, topicId, fresh = 0, lead = false }: Props = $props();
	const latest = $derived(thread.latest);
	const source = $derived(itemMeta(latest, ctx.sources).source);
	const img = $derived(lead ? thumb(latest.id, 'duotone') : null);
	const repeats = $derived(latest.title === thread.title);
</script>

<article class:lead class:dormant={thread.state === 'dormant'}>
	{#if img}<img src={img} alt="" width="160" height="90" loading="lazy" />{/if}
	<p class="kicker">
		<span>Developing story</span>
		<span>{thread.item_count} {thread.item_count === 1 ? 'update' : 'updates'}</span>
		{#if fresh > 0}<span class="new">{fresh} new</span>{/if}
		{#if thread.state === 'dormant'}<span>Dormant</span>{/if}
	</p>
	<h3><a href={ctx.href({ v: 'thread', topic: topicId, thread: thread.id })}>{thread.title}</a></h3>
	<p class="latest">
		<span class="lbl">Latest</span>
		<a href={latest.url} target="_blank" rel="noopener noreferrer"
			>{repeats ? `Read at ${source}` : latest.title}</a
		>
		<span class="src">— {source}, {relativeTime(latest.published_at, ctx.now)}</span>
	</p>
</article>

<style>
	article.dormant {
		opacity: 0.6;
	}
	img {
		display: block;
		width: 100%;
		height: auto;
		aspect-ratio: 16 / 9;
		object-fit: cover;
		margin-bottom: 0.75rem;
		filter: var(--img-filter);
	}
	.kicker {
		display: flex;
		flex-wrap: wrap;
		gap: 0 0.5rem;
		margin: 0;
		font-size: 0.7rem;
		font-weight: 600;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--red);
	}
	.kicker > * + *::before {
		content: '·';
		margin-right: 0.5rem;
		color: var(--ink-2);
	}
	.kicker .new {
		color: var(--ink);
	}
	h3 {
		margin: 0.2rem 0 0;
		font-family: var(--serif);
		font-size: 1.3rem;
		font-weight: 700;
		line-height: 1.2;
	}
	.lead h3 {
		font-size: clamp(1.7rem, 4.2vw, 2.5rem);
		line-height: 1.1;
		letter-spacing: -0.01em;
	}
	h3 a {
		text-decoration: none;
	}
	h3 a:hover,
	.latest a:hover {
		text-decoration: underline;
		text-decoration-thickness: 1px;
	}
	.latest {
		margin: 0.45rem 0 0;
		font-family: var(--serif);
		font-size: 1rem;
	}
	.lead .latest {
		font-size: 1.12rem;
	}
	.latest a {
		text-decoration: none;
	}
	.lbl {
		margin-right: 0.35rem;
		font-family: var(--sans);
		font-size: 0.68rem;
		font-weight: 700;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: var(--ink-2);
	}
	.src {
		font-style: italic;
		color: var(--ink-2);
	}
</style>
