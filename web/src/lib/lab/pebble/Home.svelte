<script lang="ts">
	import { entryItem, type LabCtx, type Tile } from '../model';
	import { thumb, topicHue } from '../thumb';

	let { tiles, ctx }: { tiles: Tile[]; ctx: LabCtx } = $props();
	const ordered = $derived(
		[...tiles].sort((a, b) => b.weight - a.weight || Number(b.active) - Number(a.active))
	);
	const totalNew = $derived(tiles.reduce((n, t) => n + t.newCount, 0));
	const withNew = $derived(tiles.filter((t) => t.newCount > 0).length);
</script>

<section class="hello">
	<h1>{totalNew > 0 ? "Here's what's new" : "You're all caught up"}</h1>
	<p>
		{#if totalNew > 0}
			{totalNew} new {totalNew === 1 ? 'story' : 'stories'} across {withNew}
			{withNew === 1 ? 'topic' : 'topics'}.
		{:else}
			Nothing new since your last look.
		{/if}
	</p>
</section>

<ul class="bento">
	{#each ordered as t (t.id)}
		{@const it = t.lead ? entryItem(t.lead) : null}
		{@const img = t.weight === 3 && it ? thumb(it.id, 'blob') : null}
		<li class="w{t.weight}" style:--h={topicHue(t.id)}>
			<a href={ctx.href({ v: 'topic', topic: t.id })}>
				{#if img}<img src={img} alt="" width="160" height="120" />{/if}
				<span class="top">
					<span class="group">{t.groupName}</span>
					{#if t.newCount > 0}<span class="pill">{t.newCount} new</span>{/if}
				</span>
				<span class="name">{t.name}</span>
				{#if !t.active}
					<span class="sub">No sources yet</span>
				{:else if t.lead && it}
					<span class="sub lead">
						{t.lead.kind === 'thread' ? t.lead.thread.title : it.title}
					</span>
					{#if t.weight >= 2 && t.lead.kind === 'thread'}
						<span class="sub latest">{it.title}</span>
					{/if}
				{:else}
					<span class="sub">Quiet for now</span>
				{/if}
				{#if t.active}
					<span class="foot">
						{t.shownCount} {t.shownCount === 1 ? 'story' : 'stories'}{t.threadCount
							? ` · ${t.threadCount} ${t.threadCount === 1 ? 'thread' : 'threads'}`
							: ''}
					</span>
				{/if}
			</a>
		</li>
	{/each}
</ul>

<p class="done"><span aria-hidden="true">✓</span> That's everything for now.</p>

<style>
	.hello {
		padding: 1rem 0 1.25rem;
	}
	h1 {
		margin: 0;
		font-size: clamp(1.9rem, 6vw, 2.8rem);
		font-weight: 800;
		line-height: 1.1;
		letter-spacing: -0.02em;
	}
	.hello p {
		margin: 0.4rem 0 0;
		font-size: 1.05rem;
		color: var(--dim);
	}
	.bento {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		grid-auto-flow: row dense;
		gap: 0.8rem;
		list-style: none;
		margin: 0;
		padding: 0;
	}
	@media (min-width: 52rem) {
		.bento {
			grid-template-columns: repeat(4, minmax(0, 1fr));
		}
		.w3 {
			grid-row: span 2;
		}
	}
	.w3,
	.w2 {
		grid-column: span 2;
	}
	li a {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		height: 100%;
		min-height: 8.5rem;
		padding: 1rem 1.1rem 1.1rem;
		border-radius: 22px;
		background: hsl(var(--h) var(--tile-s) var(--tile-l));
		box-shadow: var(--shadow);
		text-decoration: none;
		transition: transform 0.15s ease;
	}
	li a:hover {
		transform: translateY(-2px);
	}
	.w0 a {
		background: transparent;
		box-shadow: none;
		border: 2px dashed var(--chip);
		color: var(--dim);
	}
	img {
		display: block;
		width: 100%;
		height: auto;
		aspect-ratio: 4 / 3;
		max-height: 15rem;
		object-fit: cover;
		margin-bottom: 0.4rem;
		border-radius: 14px;
		filter: var(--img-filter);
	}
	.top {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 0.5rem;
	}
	.group {
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		color: hsl(var(--h) var(--pop-s) var(--pop-l));
	}
	.pill {
		padding: 0.15rem 0.6rem;
		border-radius: 999px;
		background: hsl(var(--h) var(--pop-s) var(--pop-l));
		color: var(--bg);
		font-size: 0.78rem;
		font-weight: 800;
		white-space: nowrap;
	}
	.name {
		font-size: 1.35rem;
		font-weight: 800;
		line-height: 1.15;
		letter-spacing: -0.01em;
	}
	.w3 .name {
		font-size: 1.9rem;
	}
	.sub {
		font-size: 0.92rem;
		color: var(--dim);
	}
	.lead {
		display: -webkit-box;
		overflow: hidden;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		color: var(--text);
		font-weight: 600;
	}
	.w3 .lead {
		font-size: 1.1rem;
	}
	.latest {
		display: -webkit-box;
		overflow: hidden;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
	}
	.foot {
		margin-top: auto;
		padding-top: 0.35rem;
		font-size: 0.78rem;
		color: var(--dim);
	}
	.done {
		margin: 2.5rem 0 1rem;
		text-align: center;
		color: var(--dim);
	}
	.done span {
		display: inline-grid;
		place-items: center;
		width: 1.6rem;
		height: 1.6rem;
		margin-right: 0.35rem;
		border-radius: 50%;
		background: var(--chip);
	}
</style>
