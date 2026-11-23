<script lang="ts">
	import { entryItem, type LabCtx, type Tile } from '../model';
	import { thumb } from '../thumb';

	let { tiles, ctx }: { tiles: Tile[]; ctx: LabCtx } = $props();
	// Front page: busiest topic first, then the index order; idle topics go to the foot.
	const front = $derived(
		tiles.filter((t) => t.active).sort((a, b) => b.weight - a.weight)
	);
	const idle = $derived(tiles.filter((t) => !t.active));
	const totalNew = $derived(tiles.reduce((n, t) => n + t.newCount, 0));
</script>

<h1 class="visually-hidden">Front page</h1>
<div class="frame">
	<div class="front">
		{#each front as tile (tile.id)}
			{@const it = tile.lead ? entryItem(tile.lead) : null}
			{@const img = tile.weight === 3 && it ? thumb(it.id, 'duotone') : null}
			<article class="w{tile.weight}">
				<p class="kicker">
					<span>{tile.groupName}</span>
					<a href={ctx.href({ v: 'topic', topic: tile.id })}>{tile.name}</a>
				</p>
				{#if img}<img src={img} alt="" width="160" height="90" />{/if}
				{#if tile.lead && it}
					{#if tile.lead.kind === 'thread'}
						<h2>
							<a href={ctx.href({ v: 'thread', topic: tile.id, thread: tile.lead.thread.id })}
								>{tile.lead.thread.title}</a
							>
						</h2>
						<p class="latest">
							<a href={it.url} target="_blank" rel="noopener noreferrer">{it.title}</a>
						</p>
					{:else}
						<h2><a href={it.url} target="_blank" rel="noopener noreferrer">{it.title}</a></h2>
					{/if}
					{#if tile.weight >= 2 && it.excerpt}<p class="dek">{it.excerpt}</p>{/if}
				{:else}
					<p class="dek">Nothing here in the last few days.</p>
				{/if}
				<p class="foot">
					<a href={ctx.href({ v: 'topic', topic: tile.id })}>
						{tile.newCount > 0 ? `${tile.newCount} new` : 'Up to date'}
						<span aria-hidden="true">·</span>
						{tile.shownCount}
						{tile.shownCount === 1 ? 'story' : 'stories'}
						{#if tile.threadCount}<span aria-hidden="true">·</span> {tile.threadCount}
							{tile.threadCount === 1 ? 'thread' : 'threads'}{/if}
						<span aria-hidden="true">→</span>
					</a>
				</p>
			</article>
		{/each}
	</div>
</div>

{#if idle.length}
	<p class="idle">Not in this edition (no sources yet): {idle.map((t) => t.name).join(', ')}</p>
{/if}

<p class="end">
	<span>{totalNew > 0 ? "That's the whole edition." : "You're all caught up."}</span>
</p>

<style>
	.frame {
		overflow: hidden;
		margin-top: 1.25rem;
	}
	.front {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		grid-auto-flow: row dense;
		margin: -1px 0 0 -1px;
	}
	@media (min-width: 56rem) {
		.front {
			grid-template-columns: repeat(4, minmax(0, 1fr));
		}
		.w3 {
			grid-row: span 2;
		}
	}
	article {
		min-width: 0;
		padding: 1.1rem 1.1rem 1.25rem;
		border-left: 1px solid var(--rule);
		border-top: 1px solid var(--rule);
	}
	.w3,
	.w2 {
		grid-column: span 2;
	}
	.kicker {
		display: flex;
		gap: 0.5rem;
		margin: 0 0 0.5rem;
		font-size: 0.7rem;
		font-weight: 600;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		color: var(--ink-2);
	}
	.kicker a {
		color: var(--red);
		text-decoration: none;
	}
	.kicker a::before {
		content: '/';
		margin-right: 0.5rem;
		color: var(--ink-2);
	}
	img {
		display: block;
		width: 100%;
		height: auto;
		aspect-ratio: 16 / 9;
		object-fit: cover;
		margin-bottom: 0.85rem;
		filter: var(--img-filter);
	}
	h2 {
		margin: 0;
		font-family: var(--serif);
		font-size: 1.2rem;
		font-weight: 700;
		line-height: 1.2;
	}
	.w2 h2 {
		font-size: 1.5rem;
	}
	.w3 h2 {
		font-size: clamp(1.8rem, 4.5vw, 2.6rem);
		line-height: 1.08;
		letter-spacing: -0.015em;
	}
	h2 a,
	.latest a,
	.foot a {
		text-decoration: none;
	}
	h2 a:hover,
	.latest a:hover,
	.foot a:hover {
		text-decoration: underline;
		text-decoration-thickness: 1px;
	}
	.latest {
		margin: 0.4rem 0 0;
		font-family: var(--serif);
		font-style: italic;
		color: var(--ink-2);
	}
	.dek {
		margin: 0.5rem 0 0;
		font-family: var(--serif);
		font-size: 1rem;
		color: var(--ink-2);
	}
	.w3 .dek {
		font-size: 1.1rem;
	}
	.foot {
		margin: 0.6rem 0 0;
		font-size: 0.78rem;
		color: var(--ink-2);
	}
	.foot a {
		display: inline-flex;
		gap: 0.35rem;
		align-items: center;
		min-height: 44px;
	}
	.idle {
		margin: 0;
		padding: 0.75rem 0;
		border-top: 1px solid var(--rule);
		font-size: 0.8rem;
		font-style: italic;
		color: var(--ink-2);
	}
	.end {
		display: flex;
		align-items: center;
		gap: 1rem;
		margin: 2.5rem 0 1rem;
		font-family: var(--serif);
		font-style: italic;
		color: var(--ink-2);
	}
	.end::before,
	.end::after {
		content: '';
		flex: 1;
		border-top: 1px solid var(--rule);
	}
</style>
