<script lang="ts">
	// Spine and branches as a git-style lane graph, newest first: the storyline on
	// lane 0, side developments forking onto lane 1, related threads as refs.
	import type { ExportItem } from '$lib/types';
	import { age, clock, itemMeta, shortDay, type LabCtx } from '../model';
	import type { Spine } from '../spine';

	let { spine, ctx }: { spine: Spine; ctx: LabCtx } = $props();

	type Row = { item: ExportItem; side: boolean };
	// Newest first: a node's side developments are later than it, so they sit above it.
	const rows = $derived(
		[...spine.nodes]
			.reverse()
			.flatMap((n): Row[] => [
				...[...n.branches].reverse().map((item) => ({ item, side: true })),
				{ item: n.item, side: false }
			])
	);
	const updates = $derived(spine.nodes.length + spine.branchCount);
</script>

<header>
	<a class="up" href={ctx.href({ v: 'topic', topic: spine.topicId })}>cd ..</a>
	<h1>{spine.title}</h1>
	<p class="kv">
		<span><i>id</i> {spine.id.slice(0, 7)}</span>
		<span><i>state</i> {spine.state}</span>
		<span><i>updates</i> {updates} ({spine.nodes.length} spine, {spine.branchCount} side)</span>
		<span><i>since</i> {shortDay(spine.createdAt)}</span>
	</p>
	<p class="mock"># layout mock: branch structure is invented from the sample thread</p>
</header>

<ol class="graph">
	<li class="row head">
		<span class="dot" aria-hidden="true"></span>
		<span class="ref">HEAD → now · you're caught up</span>
	</li>
	{#each rows as r (r.item.id)}
		{@const m = itemMeta(r.item, ctx.sources)}
		<li class="row" class:side={r.side}>
			{#if r.side}
				<svg class="fork" viewBox="0 0 40 100" preserveAspectRatio="none" aria-hidden="true">
					<path d="M30 0 V35 C30 70 10 65 10 100" vector-effect="non-scaling-stroke" />
				</svg>
			{/if}
			<span class="dot" aria-hidden="true"></span>
			<div class="commit">
				<p class="line">
					<span class="hash">{r.item.id.slice(0, 7)}</span>
					<span class="when">{shortDay(r.item.published_at)} {clock(r.item.published_at)}</span>
					{#if r.side}<span class="tag">side</span>{/if}
				</p>
				<a class="title" href={r.item.url} target="_blank" rel="noopener noreferrer">{r.item.title}</a>
				<p class="src">{m.source} · {age(r.item.published_at, ctx.now)} ago</p>
			</div>
		</li>
	{/each}
</ol>

<section aria-labelledby="lg-refs">
	<h2 id="lg-refs">refs</h2>
	{#if spine.related.length}
		<ul class="refs">
			{#each spine.related as r (r.id)}
				<li>
					<a href={ctx.href({ v: 'thread', topic: spine.topicId, thread: r.id })}>
						<span class="arrow" aria-hidden="true">→</span>
						<span class="rt">{r.title}</span>
						<span class="rn">[{r.itemCount}] {r.state} · {age(r.lastItemAt, ctx.now)}</span>
					</a>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="src">no related threads</p>
	{/if}
</section>

<style>
	header {
		margin: 0.5rem 0 1rem;
	}
	.up {
		display: inline-flex;
		align-items: center;
		min-height: 44px;
		font-size: 0.8rem;
		color: var(--teal);
	}
	h1 {
		margin: 0;
		font-family: var(--cond);
		font-stretch: condensed;
		font-size: clamp(1.6rem, 5vw, 2.2rem);
		line-height: 1.1;
	}
	.kv {
		display: flex;
		flex-wrap: wrap;
		gap: 0 1rem;
		margin: 0.4rem 0 0;
		font-size: 0.78rem;
	}
	i {
		font-style: normal;
		color: var(--dim);
	}
	i::after {
		content: ':';
	}
	.mock {
		margin: 0.4rem 0 0;
		font-size: 0.75rem;
		color: var(--dim);
	}
	.graph {
		--lane0: 10px;
		--lane1: 30px;
		list-style: none;
		margin: 0;
		padding: 0;
		border-top: 1px solid var(--line);
	}
	.row {
		position: relative;
		padding: 0.6rem 0 0.6rem 3.25rem;
		border-bottom: 1px solid var(--line);
	}
	/* Lane 0, the storyline, runs through every row. */
	.row::before {
		content: '';
		position: absolute;
		left: calc(var(--lane0) - 1px);
		top: 0;
		bottom: 0;
		border-left: 2px solid var(--teal);
	}
	.head::before {
		top: 1.05rem;
	}
	.row:last-child::before {
		bottom: auto;
		height: 1.05rem;
	}
	.dot {
		position: absolute;
		left: calc(var(--lane0) - 5px);
		top: calc(0.6rem + 0.15rem);
		width: 10px;
		height: 10px;
		border-radius: 50%;
		background: var(--bg);
		border: 2px solid var(--teal);
	}
	.head .dot {
		background: var(--amber);
		border-color: var(--amber);
	}
	.side .dot {
		left: calc(var(--lane1) - 5px);
		border-color: var(--amber);
	}
	.fork {
		position: absolute;
		left: 0;
		top: 1.05rem;
		width: 40px;
		height: calc(100% - 1.05rem);
		overflow: visible;
	}
	.fork path {
		fill: none;
		stroke: var(--amber);
		stroke-width: 2;
	}
	.ref {
		font-size: 0.78rem;
		color: var(--amber);
	}
	.line {
		display: flex;
		flex-wrap: wrap;
		gap: 0 0.75rem;
		margin: 0;
		font-size: 0.75rem;
		color: var(--dim);
	}
	.hash {
		color: var(--amber);
	}
	.tag {
		padding: 0 0.35rem;
		border: 1px solid var(--amber);
		color: var(--amber);
	}
	.title {
		display: block;
		margin-top: 0.1rem;
		font-family: var(--cond);
		font-stretch: condensed;
		font-size: 1.1rem;
		font-weight: 600;
		line-height: 1.25;
		text-decoration: none;
	}
	.side .title {
		font-weight: 500;
	}
	.title:hover {
		color: var(--teal);
		text-decoration: underline;
	}
	.src {
		margin: 0.1rem 0 0;
		font-size: 0.75rem;
		color: var(--dim);
	}
	section {
		margin-top: 1.5rem;
	}
	h2 {
		margin: 0 0 0.25rem;
		font-size: 0.72rem;
		font-weight: 600;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--dim);
	}
	h2::before {
		content: '── ';
	}
	.refs {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.refs a {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0 0.6rem;
		min-height: 44px;
		text-decoration: none;
	}
	.refs a:hover .rt {
		color: var(--teal);
		text-decoration: underline;
	}
	.arrow {
		color: var(--teal);
	}
	.rt {
		font-family: var(--cond);
		font-stretch: condensed;
		font-size: 1.05rem;
		font-weight: 600;
	}
	.rn {
		font-size: 0.75rem;
		color: var(--dim);
	}
</style>
