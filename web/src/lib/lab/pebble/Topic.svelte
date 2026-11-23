<script lang="ts">
	import { dayLabel } from '$lib/time';
	import { showNew, threadNew, visitSummary, type LabCtx, type Tile, type TopicView } from '../model';
	import { topicHue } from '../thumb';
	import ItemCard from './ItemCard.svelte';
	import ThreadCard from './ThreadCard.svelte';

	let { topic, tiles, ctx }: { topic: TopicView; tiles: Tile[]; ctx: LabCtx } = $props();
	const feed = $derived(topic.feed);
	const since = $derived(ctx.lastSeen[feed.id]);
	const group = $derived(tiles.find((t) => t.id === feed.id)?.groupName ?? '');
	let showMore = $state(false);
</script>

<div class="topic" style:--h={topicHue(feed.id)}>
	<header>
		<a class="back" href={ctx.href({ v: 'home' })}><span aria-hidden="true">←</span> Home</a>
		<p class="group">{group}</p>
		<h1>{feed.name}</h1>
		<p class="summary">{visitSummary(feed, since)}</p>
	</header>

	{#if topic.layout}
		<ul class="masonry">
			{#each topic.layout.live as e (e.id)}
				<li>
					{#if e.kind === 'thread'}
						<ThreadCard thread={e.thread} {ctx} topicId={feed.id} fresh={threadNew(e.thread, since)} />
					{:else}
						<ItemCard item={e.item} {ctx} isNew={showNew(e.item, since)} />
					{/if}
				</li>
			{/each}
			{#if showMore}
				{#each topic.layout.moreItems as item (item.id)}
					<li><ItemCard {item} {ctx} isNew={showNew(item, since)} /></li>
				{/each}
			{/if}
		</ul>
		{#if topic.layout.moreItems.length}
			<button type="button" class="pillbtn" aria-expanded={showMore} onclick={() => (showMore = !showMore)}>
				{showMore ? 'Show fewer' : `+${topic.layout.moreItems.length} more single stories`}
			</button>
		{/if}

		{#if topic.layout.cooling.length}
			<h2>Quiet lately</h2>
			<ul class="masonry">
				{#each topic.layout.cooling as t (t.id)}
					<li><ThreadCard thread={t} {ctx} topicId={feed.id} fresh={threadNew(t, since)} /></li>
				{/each}
			</ul>
		{/if}

		{#if topic.layout.dormant.length}
			<details>
				<summary class="pillbtn">
					Show {topic.layout.dormant.length} dormant {topic.layout.dormant.length === 1 ? 'thread' : 'threads'}
				</summary>
				<ul class="masonry">
					{#each topic.layout.dormant as t (t.id)}
						<li><ThreadCard thread={t} {ctx} topicId={feed.id} /></li>
					{/each}
				</ul>
			</details>
		{/if}
	{:else}
		{#each topic.days as day (day.key)}
			<h2>{dayLabel(day.key, ctx.now)}</h2>
			<ul class="masonry">
				{#each [...day.shown, ...day.more] as item (item.id)}
					<li><ItemCard {item} {ctx} isNew={showNew(item, since)} /></li>
				{/each}
			</ul>
		{/each}
	{/if}

	{#if topic.empty}<p class="summary">Nothing here in the last few days.</p>{/if}

	<p class="done"><span aria-hidden="true">✓</span> You're all caught up.</p>
</div>

<style>
	header {
		margin: 0.25rem 0 1.25rem;
		padding: 1rem 1.25rem 1.4rem;
		border-radius: 28px;
		background: hsl(var(--h) var(--tile-s) var(--tile-l));
	}
	.back {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		min-height: 44px;
		padding: 0 0.9rem;
		border-radius: 999px;
		background: var(--surface);
		font-size: 0.88rem;
		font-weight: 700;
		text-decoration: none;
	}
	.group {
		margin: 0.9rem 0 0;
		font-size: 0.8rem;
		font-weight: 700;
		color: hsl(var(--h) var(--pop-s) var(--pop-l));
	}
	h1 {
		margin: 0;
		font-size: clamp(2.2rem, 7vw, 3.2rem);
		font-weight: 800;
		line-height: 1.05;
		letter-spacing: -0.02em;
	}
	.summary {
		margin: 0.35rem 0 0;
		color: var(--dim);
	}
	.masonry {
		columns: 18rem;
		column-gap: 0.9rem;
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.masonry li {
		break-inside: avoid;
		margin-bottom: 0.9rem;
	}
	h2 {
		margin: 1.75rem 0 0.75rem;
		font-size: 1.15rem;
		font-weight: 800;
	}
	.pillbtn {
		display: inline-flex;
		align-items: center;
		min-height: 44px;
		padding: 0 1.1rem;
		border: 0;
		border-radius: 999px;
		background: var(--chip);
		color: var(--text);
		font: inherit;
		font-size: 0.9rem;
		font-weight: 700;
		cursor: pointer;
	}
	details {
		margin-top: 1.5rem;
	}
	summary {
		list-style: none;
		margin-bottom: 0.9rem;
	}
	summary::-webkit-details-marker {
		display: none;
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
