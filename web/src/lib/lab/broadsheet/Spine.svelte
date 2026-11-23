<script lang="ts">
	// Spine and branches as a classic vertical timeline: dates in the margin,
	// side developments as indented marginalia, related threads in a "See also" rail.
	import { relativeTime } from '$lib/time';
	import { clock, shortDay, weekday, type LabCtx, type Tile } from '../model';
	import type { Spine } from '../spine';
	import Meta from './Meta.svelte';

	let { spine, tiles, ctx }: { spine: Spine; tiles: Tile[]; ctx: LabCtx } = $props();
	const topicName = $derived(tiles.find((t) => t.id === spine.topicId)?.name ?? spine.topicId);
	const updates = $derived(spine.nodes.length + spine.branchCount);
</script>

<nav class="crumbs">
	<a href={ctx.href({ v: 'topic', topic: spine.topicId })}>← {topicName}</a>
</nav>
<header>
	<p class="kicker">Developing story · {spine.state}</p>
	<h1>{spine.title}</h1>
	<p class="standfirst">
		{updates} updates since {weekday(spine.createdAt)}, {shortDay(spine.createdAt)}. Last update
		{relativeTime(spine.lastItemAt, ctx.now)}.
	</p>
	<p class="mock">Layout mock: the branch structure is invented from the sample thread.</p>
</header>

<div class="layout">
	<ol class="timeline">
		{#each spine.nodes as node (node.item.id)}
			<li class="node">
				<div class="when">
					<span class="day"
						><span class="wd">{weekday(node.item.published_at)}</span>
						{shortDay(node.item.published_at)}</span
					>
					<span class="time">{clock(node.item.published_at)}</span>
				</div>
				<div class="what">
					<h2>
						<a href={node.item.url} target="_blank" rel="noopener noreferrer">{node.item.title}</a>
					</h2>
					{#if node.item.excerpt}<p class="dek">{node.item.excerpt}</p>{/if}
					<Meta item={node.item} {ctx} />
					{#if node.branches.length}
						<ul class="branches">
							{#each node.branches as b (b.id)}
								<li>
									<p class="side">Side development · {clock(b.published_at)}</p>
									<h3><a href={b.url} target="_blank" rel="noopener noreferrer">{b.title}</a></h3>
									<Meta item={b} {ctx} />
								</li>
							{/each}
						</ul>
					{/if}
				</div>
			</li>
		{/each}
		<li class="node now">
			<div class="when"><span class="time">Now</span></div>
			<div class="what"><p class="caught">You're caught up on this story.</p></div>
		</li>
	</ol>

	<aside aria-labelledby="bs-see-also">
		<h2 id="bs-see-also">See also</h2>
		{#if spine.related.length}
			<ul>
				{#each spine.related as r (r.id)}
					<li>
						<a href={ctx.href({ v: 'thread', topic: spine.topicId, thread: r.id })}>{r.title}</a>
						<span>{r.itemCount} updates · {r.state} · {relativeTime(r.lastItemAt, ctx.now)}</span>
					</li>
				{/each}
			</ul>
		{:else}
			<p class="none">No related threads in {topicName}.</p>
		{/if}
	</aside>
</div>

<style>
	.crumbs a {
		display: inline-flex;
		align-items: center;
		min-height: 44px;
		font-size: 0.8rem;
		color: var(--ink-2);
		text-decoration: none;
	}
	header {
		max-width: 46rem;
		padding-bottom: 1.25rem;
	}
	.kicker {
		margin: 0;
		font-size: 0.72rem;
		font-weight: 600;
		letter-spacing: 0.16em;
		text-transform: uppercase;
		color: var(--red);
	}
	h1 {
		margin: 0.2rem 0 0;
		font-family: var(--serif);
		font-size: clamp(2rem, 6.5vw, 3.2rem);
		line-height: 1.05;
		letter-spacing: -0.015em;
	}
	.standfirst {
		margin: 0.6rem 0 0;
		font-family: var(--serif);
		font-size: 1.15rem;
		color: var(--ink-2);
	}
	.mock {
		display: inline-block;
		margin: 0.75rem 0 0;
		padding: 0.15rem 0.5rem;
		border: 1px dashed var(--rule);
		font-size: 0.72rem;
		color: var(--ink-2);
	}
	.layout {
		display: grid;
		gap: 2rem;
		border-top: 3px double var(--rule-strong);
		padding-top: 1.5rem;
	}
	@media (min-width: 56rem) {
		.layout {
			grid-template-columns: minmax(0, 1fr) 17rem;
			gap: 3rem;
		}
	}
	.timeline {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.node {
		--gutter: 1rem;
		--indent: 0.25rem;
		display: grid;
		grid-template-columns: 3.25rem minmax(0, 1fr);
		column-gap: 0.75rem;
	}
	.wd {
		display: none;
	}
	@media (min-width: 40rem) {
		.node {
			--gutter: 1.5rem;
			--indent: 1.25rem;
			grid-template-columns: 6.5rem minmax(0, 1fr);
			column-gap: 1.5rem;
		}
		.wd {
			display: inline;
		}
	}
	.when {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		padding-top: 0.2rem;
		text-align: right;
	}
	.day {
		font-size: 0.68rem;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: var(--ink-2);
	}
	.time {
		font-family: var(--serif);
		font-size: 1.05rem;
		font-variant-numeric: oldstyle-nums;
	}
	.what {
		position: relative;
		padding: 0 0 2rem var(--gutter);
		border-left: 1px solid var(--rule-strong);
	}
	.what::before {
		content: '';
		position: absolute;
		left: -5px;
		top: 0.5rem;
		width: 9px;
		height: 9px;
		border-radius: 50%;
		background: var(--paper);
		border: 1px solid var(--rule-strong);
	}
	.node:first-child .what::before {
		background: var(--rule-strong);
	}
	.now .what {
		border-left-color: transparent;
	}
	.now .what::before {
		background: var(--red);
		border-color: var(--red);
	}
	.now .time {
		color: var(--red);
		font-style: italic;
	}
	h2 {
		margin: 0;
		font-family: var(--serif);
		font-size: 1.3rem;
		line-height: 1.2;
	}
	h2 a,
	h3 a,
	aside a {
		text-decoration: none;
	}
	h2 a:hover,
	h3 a:hover,
	aside a:hover {
		text-decoration: underline;
		text-decoration-thickness: 1px;
	}
	.dek {
		margin: 0.35rem 0 0;
		font-family: var(--serif);
		color: var(--ink-2);
	}
	.branches {
		list-style: none;
		margin: 1rem 0 0;
		padding: 0;
	}
	.branches li {
		position: relative;
		margin-left: var(--indent);
		padding: 0.1rem 0 0.1rem 1rem;
		border-left: 1px dashed var(--ink-2);
	}
	.branches li::before {
		content: '';
		position: absolute;
		left: calc(-1 * (var(--gutter) + var(--indent)));
		top: 0.7rem;
		width: calc(var(--gutter) + var(--indent) - 0.15rem);
		border-top: 1px dashed var(--ink-2);
	}
	.branches li + li {
		margin-top: 0.75rem;
	}
	.side {
		margin: 0;
		font-size: 0.68rem;
		font-weight: 600;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--red);
	}
	h3 {
		margin: 0.1rem 0 0;
		font-family: var(--serif);
		font-size: 1.05rem;
		font-style: italic;
		font-weight: 600;
	}
	.caught {
		margin: 0.1rem 0 0;
		font-family: var(--serif);
		font-style: italic;
		color: var(--ink-2);
	}
	aside h2 {
		padding-bottom: 0.4rem;
		border-bottom: 2px solid var(--rule-strong);
		font-family: var(--sans);
		font-size: 0.75rem;
		letter-spacing: 0.16em;
		text-transform: uppercase;
	}
	aside ul {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	aside li {
		padding: 0.75rem 0;
		border-bottom: 1px solid var(--rule);
	}
	aside li a {
		display: block;
		font-family: var(--serif);
		font-size: 1.1rem;
		font-weight: 600;
		line-height: 1.25;
		min-height: 44px;
	}
	aside li span,
	.none {
		font-size: 0.78rem;
		color: var(--ink-2);
	}
</style>
