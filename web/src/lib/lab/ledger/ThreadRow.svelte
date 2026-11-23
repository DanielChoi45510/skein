<script lang="ts">
	// A thread as a row that expands (no JS) to its newest headline.
	import type { ThreadSummary } from '$lib/types';
	import { age, itemMeta, type LabCtx } from '../model';

	interface Props {
		thread: ThreadSummary;
		ctx: LabCtx;
		topicId: string;
		fresh?: number;
	}
	let { thread, ctx, topicId, fresh = 0 }: Props = $props();
	const latest = $derived(thread.latest);
	const source = $derived(itemMeta(latest, ctx.sources).source);
</script>

<details class:dormant={thread.state === 'dormant'}>
	<summary>
		<span class="t" class:new={fresh > 0}>{age(thread.last_item_at, ctx.now)}</span>
		<span class="glyph" aria-hidden="true">▸</span>
		<span class="title">{thread.title}</span>
		<span class="n"
			>[{thread.item_count}]{#if fresh > 0}<b> +{fresh}</b>{/if}</span
		>
	</summary>
	<div class="body">
		<p>
			<i>latest</i>
			<a href={latest.url} target="_blank" rel="noopener noreferrer">{latest.title}</a>
			<span class="dim">({source}, {age(latest.published_at, ctx.now)})</span>
		</p>
		<p>
			<i>state</i> <span>{thread.state}</span> <i>kind</i> <span>{thread.kind}</span>
		</p>
		<a class="open" href={ctx.href({ v: 'thread', topic: topicId, thread: thread.id })}
			>open thread → {thread.id.slice(0, 7)}</a
		>
	</div>
</details>

<style>
	summary {
		display: grid;
		grid-template-columns: 2.5rem 2.75rem minmax(0, 1fr) auto;
		gap: 0.6rem;
		align-items: center;
		min-height: 44px;
		padding: 0.35rem 0;
		cursor: pointer;
		list-style: none;
	}
	summary::-webkit-details-marker {
		display: none;
	}
	.t {
		font-size: 0.78rem;
		text-align: right;
		color: var(--dim);
	}
	.t.new {
		color: var(--amber);
	}
	.glyph {
		justify-self: center;
		color: var(--teal);
		transition: transform 0.15s;
	}
	details[open] .glyph {
		transform: rotate(90deg);
	}
	.title {
		font-family: var(--cond);
		font-stretch: condensed;
		font-size: 1.1rem;
		font-weight: 700;
	}
	.n {
		font-size: 0.78rem;
		color: var(--dim);
		font-variant-numeric: tabular-nums;
	}
	.n b {
		color: var(--amber);
	}
	.dormant {
		opacity: 0.6;
	}
	.body {
		margin: 0 0 0.5rem 5.95rem;
		padding: 0.25rem 0 0.25rem 0.75rem;
		border-left: 1px solid var(--teal);
		font-size: 0.8rem;
	}
	.body p {
		margin: 0.2rem 0;
	}
	i {
		font-style: normal;
		color: var(--dim);
	}
	i::after {
		content: ':';
	}
	.body a {
		text-decoration: none;
	}
	.body a:hover {
		text-decoration: underline;
		color: var(--teal);
	}
	.dim {
		color: var(--dim);
	}
	.open {
		display: inline-flex;
		align-items: center;
		min-height: 44px;
		color: var(--teal);
	}
</style>
