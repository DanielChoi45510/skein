<script lang="ts">
	// A thread as a stacked "deck" of cards: the top card is the story so far.
	import type { ThreadSummary } from '$lib/types';
	import { relativeTime } from '$lib/time';
	import { itemMeta, type LabCtx } from '../model';

	interface Props {
		thread: ThreadSummary;
		ctx: LabCtx;
		topicId: string;
		fresh?: number;
	}
	let { thread, ctx, topicId, fresh = 0 }: Props = $props();
	const latest = $derived(thread.latest);
	const source = $derived(itemMeta(latest, ctx.sources).source);
	const href = $derived(ctx.href({ v: 'thread', topic: topicId, thread: thread.id }));
</script>

<div class="deck" class:dormant={thread.state === 'dormant'}>
	<article>
		<p class="chips">
			<span class="chip story">Story · {thread.item_count} updates</span>
			{#if fresh > 0}<span class="chip new">{fresh} new</span>{/if}
			{#if thread.state !== 'active'}<span class="chip">{thread.state}</span>{/if}
		</p>
		<h3><a {href}>{thread.title}</a></h3>
		<a class="latest" href={latest.url} target="_blank" rel="noopener noreferrer">
			<span class="lbl">Latest</span>
			<span class="t">{latest.title}</span>
			<span class="s">{source} · {relativeTime(latest.published_at, ctx.now)}</span>
		</a>
		<a class="open" {href}>Follow the story <span aria-hidden="true">→</span></a>
	</article>
</div>

<style>
	.deck {
		position: relative;
		padding-bottom: 12px;
	}
	/* Two cards peeking out underneath. */
	.deck::before,
	.deck::after {
		content: '';
		position: absolute;
		left: 14px;
		right: 14px;
		bottom: 6px;
		height: 30px;
		border-radius: 0 0 20px 20px;
		background: hsl(var(--h) var(--tile-s) var(--tile-l));
		filter: brightness(0.92);
	}
	.deck::after {
		left: 28px;
		right: 28px;
		bottom: 0;
		filter: brightness(0.84);
	}
	.dormant {
		opacity: 0.6;
	}
	article {
		position: relative;
		z-index: 1;
		padding: 1rem 1.1rem 0.75rem;
		border-radius: 22px;
		background: hsl(var(--h) var(--tile-s) var(--tile-l));
		box-shadow: var(--shadow);
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
		background: var(--surface);
		font-size: 0.72rem;
		font-weight: 700;
		color: var(--dim);
	}
	.chip.story {
		color: hsl(var(--h) var(--pop-s) var(--pop-l));
	}
	.chip.new {
		background: hsl(var(--h) var(--pop-s) var(--pop-l));
		color: var(--bg);
	}
	h3 {
		margin: 0.5rem 0 0;
		font-size: 1.3rem;
		font-weight: 800;
		line-height: 1.2;
		letter-spacing: -0.01em;
	}
	h3 a {
		display: block;
		min-height: 44px;
		text-decoration: none;
	}
	.latest {
		display: flex;
		flex-direction: column;
		margin-top: 0.25rem;
		padding: 0.6rem 0.8rem;
		border-radius: 14px;
		background: var(--surface);
		text-decoration: none;
	}
	.latest:hover .t {
		text-decoration: underline;
	}
	.lbl {
		font-size: 0.7rem;
		font-weight: 700;
		color: var(--dim);
	}
	.t {
		font-weight: 600;
		line-height: 1.3;
	}
	.s {
		font-size: 0.78rem;
		color: var(--dim);
	}
	.open {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		min-height: 44px;
		font-size: 0.88rem;
		font-weight: 700;
		color: hsl(var(--h) var(--pop-s) var(--pop-l));
		text-decoration: none;
	}
</style>
