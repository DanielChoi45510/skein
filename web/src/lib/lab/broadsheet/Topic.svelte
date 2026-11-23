<script lang="ts">
	import { dayLabel } from '$lib/time';
	import { showNew, splitLead, threadNew, visitSummary, type LabCtx, type Tile, type TopicView } from '../model';
	import ItemCard from './ItemCard.svelte';
	import ThreadCard from './ThreadCard.svelte';

	let { topic, tiles, ctx }: { topic: TopicView; tiles: Tile[]; ctx: LabCtx } = $props();
	const feed = $derived(topic.feed);
	const since = $derived(ctx.lastSeen[feed.id]);
	const group = $derived(tiles.find((t) => t.id === feed.id)?.groupName ?? '');
	const split = $derived(splitLead(topic.layout?.live ?? []));
	const lead = $derived(split.lead);
	const rest = $derived(split.rest);
	let showMore = $state(false);
</script>

<nav class="crumbs"><a href={ctx.href({ v: 'home' })}>← Front page</a></nav>
<header>
	<p class="kicker">{group}</p>
	<h1>{feed.name}</h1>
	<p class="summary">{visitSummary(feed, since)}</p>
</header>

{#if topic.layout}
	{#if lead}
		<div class="lead">
			{#if lead.kind === 'thread'}
				<ThreadCard thread={lead.thread} {ctx} topicId={feed.id} fresh={threadNew(lead.thread, since)} lead />
			{:else}
				<ItemCard item={lead.item} {ctx} isNew={showNew(lead.item, since)} lead />
			{/if}
		</div>
	{/if}
	{#if rest.length || (showMore && topic.layout.moreItems.length)}
		<ul class="cols">
			{#each rest as e (e.id)}
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
	{/if}
	{#if topic.layout.moreItems.length}
		<button type="button" class="more" aria-expanded={showMore} onclick={() => (showMore = !showMore)}>
			{showMore ? 'Show fewer' : `+${topic.layout.moreItems.length} more single stories`}
		</button>
	{/if}

	{#if topic.layout.cooling.length}
		<section aria-labelledby="bs-cooling">
			<h2 id="bs-cooling">Quiet lately</h2>
			<ul class="cols">
				{#each topic.layout.cooling as t (t.id)}
					<li><ThreadCard thread={t} {ctx} topicId={feed.id} fresh={threadNew(t, since)} /></li>
				{/each}
			</ul>
		</section>
	{/if}

	{#if topic.layout.dormant.length}
		<details>
			<summary>
				{topic.layout.dormant.length} dormant {topic.layout.dormant.length === 1 ? 'thread' : 'threads'}
			</summary>
			<ul class="cols">
				{#each topic.layout.dormant as t (t.id)}
					<li><ThreadCard thread={t} {ctx} topicId={feed.id} /></li>
				{/each}
			</ul>
		</details>
	{/if}
{:else}
	{#each topic.days as day (day.key)}
		<section aria-labelledby="bs-day-{day.key}">
			<h2 id="bs-day-{day.key}">{dayLabel(day.key, ctx.now)}</h2>
			<ul class="cols">
				{#each [...day.shown, ...day.more] as item (item.id)}
					<li><ItemCard {item} {ctx} isNew={showNew(item, since)} /></li>
				{/each}
			</ul>
		</section>
	{/each}
{/if}

{#if topic.empty}<p class="summary">Nothing here in the last few days.</p>{/if}

<p class="end"><span>You're all caught up.</span></p>

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
		padding: 0.5rem 0 1.25rem;
		border-bottom: 1px solid var(--rule-strong);
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
		margin: 0.1rem 0 0;
		font-family: var(--serif);
		font-size: clamp(2.4rem, 8vw, 3.6rem);
		font-weight: 700;
		line-height: 1;
		letter-spacing: -0.02em;
	}
	.summary {
		margin: 0.5rem 0 0;
		font-family: var(--serif);
		font-style: italic;
		color: var(--ink-2);
	}
	.lead {
		max-width: 46rem;
		padding: 1.5rem 0;
		border-bottom: 1px solid var(--rule);
	}
	.cols {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.cols li {
		padding: 1.1rem 0;
		border-bottom: 1px solid var(--rule);
	}
	@media (min-width: 56rem) {
		.cols {
			grid-template-columns: repeat(2, minmax(0, 1fr));
			column-gap: 2.5rem;
		}
	}
	section {
		margin-top: 2rem;
	}
	h2,
	summary {
		margin: 0;
		padding-bottom: 0.4rem;
		border-bottom: 2px solid var(--rule-strong);
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.16em;
		text-transform: uppercase;
	}
	details {
		margin-top: 2rem;
	}
	summary {
		display: flex;
		align-items: center;
		min-height: 44px;
		cursor: pointer;
		color: var(--ink-2);
	}
	.more {
		min-height: 44px;
		margin-top: 0.5rem;
		padding: 0;
		border: 0;
		background: none;
		font-family: var(--serif);
		font-style: italic;
		text-decoration: underline;
		text-underline-offset: 0.2em;
		color: var(--ink-2);
		cursor: pointer;
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
