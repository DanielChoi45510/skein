<script lang="ts">
	import { entryItem, tilesByGroup, type LabCtx, type Tile } from '../model';

	let { tiles, ctx }: { tiles: Tile[]; ctx: LabCtx } = $props();
	const groups = $derived(tilesByGroup(tiles));
	const totalNew = $derived(tiles.reduce((n, t) => n + t.newCount, 0));
	const totalShown = $derived(tiles.reduce((n, t) => n + t.shownCount, 0));
	const live = $derived(tiles.filter((t) => t.active).length);
	const peak = $derived(Math.max(1, ...tiles.flatMap((t) => t.perDay)));
</script>

<h1 class="visually-hidden">Topics</h1>
<p class="stats">
	<span><b class="new">{totalNew}</b> new</span>
	<span><b>{totalShown}</b> shown</span>
	<span><b>{live}</b>/{tiles.length} topics live</span>
</p>

{#each groups as g (g.id)}
	<section aria-labelledby="lg-{g.id}">
		<h2 id="lg-{g.id}">{g.name}</h2>
		<ul class="grid">
			{#each g.tiles as t (t.id)}
				{@const it = t.lead ? entryItem(t.lead) : null}
				<li class:idle={!t.active}>
					<a href={ctx.href({ v: 'topic', topic: t.id })}>
						<span class="row">
							<span class="name">{t.name}</span>
							<span class="mode">{t.mode}</span>
						</span>
						{#if t.active}
							<span class="count" class:has={t.newCount > 0}>
								{t.newCount > 0 ? t.newCount : '—'}<small>new</small>
							</span>
							<span
								class="bars"
								role="img"
								aria-label="Stories per day, last 7 days: {t.perDay.join(', ')}"
							>
								{#each t.perDay as n, i (i)}
									<span style:height="{Math.max(6, (n / peak) * 100)}%" class:zero={n === 0}></span>
								{/each}
							</span>
							<span class="row foot">
								<span>{t.shownCount} shown</span>
								<span>{t.threadCount} thr</span>
							</span>
							{#if it}
								<span class="lead"
									>{t.lead?.kind === 'thread' ? t.lead.thread.title : it.title}</span
								>
							{/if}
						{:else}
							<span class="none">no sources</span>
						{/if}
					</a>
				</li>
			{/each}
		</ul>
	</section>
{/each}

<p class="eof">-- end of feed · {totalNew > 0 ? "that's everything" : "you're all caught up"} --</p>

<style>
	.stats {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem 1.25rem;
		margin: 1rem 0 0;
		color: var(--dim);
	}
	.stats b {
		color: var(--text);
		font-variant-numeric: tabular-nums;
	}
	.stats b.new {
		color: var(--amber);
	}
	section {
		margin-top: 1.25rem;
	}
	h2 {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		margin: 0 0 0.5rem;
		font-size: 0.72rem;
		font-weight: 600;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--dim);
	}
	h2::before {
		content: '──';
	}
	h2::after {
		content: '';
		flex: 1;
		border-top: 1px solid var(--line);
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 1px;
		list-style: none;
		margin: 0;
		padding: 1px;
	}
	@media (min-width: 48rem) {
		.grid {
			grid-template-columns: repeat(4, minmax(0, 1fr));
		}
	}
	li {
		outline: 1px solid var(--line);
		background: var(--panel);
	}
	li a {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		height: 100%;
		min-height: 44px;
		padding: 0.6rem 0.7rem 0.7rem;
		text-decoration: none;
	}
	li a:hover {
		background: color-mix(in srgb, var(--teal) 8%, transparent);
	}
	.idle {
		background: transparent;
	}
	.idle a {
		color: var(--dim);
	}
	.row {
		display: flex;
		justify-content: space-between;
		gap: 0.5rem;
	}
	.name {
		font-family: var(--cond);
		font-stretch: condensed;
		font-size: 1.05rem;
		font-weight: 700;
	}
	.mode {
		font-size: 0.68rem;
		color: var(--dim);
	}
	.count {
		font-size: 1.9rem;
		font-weight: 600;
		line-height: 1;
		font-variant-numeric: tabular-nums;
		color: var(--dim);
	}
	.count.has {
		color: var(--amber);
	}
	.count small {
		margin-left: 0.35rem;
		font-size: 0.7rem;
		font-weight: 400;
		color: var(--dim);
	}
	.bars {
		display: flex;
		align-items: flex-end;
		gap: 2px;
		height: 1.4rem;
	}
	.bars span {
		flex: 1;
		background: var(--teal);
		opacity: 0.85;
	}
	.bars span.zero {
		background: var(--line);
	}
	.foot {
		font-size: 0.72rem;
		color: var(--dim);
	}
	.lead {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-size: 0.75rem;
		color: var(--dim);
		border-top: 1px dashed var(--line);
		padding-top: 0.35rem;
	}
	.none {
		font-size: 0.75rem;
	}
	.eof {
		margin: 2rem 0;
		text-align: center;
		color: var(--dim);
	}
</style>
