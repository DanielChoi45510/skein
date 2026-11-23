<script lang="ts">
	import { dayLabel } from '$lib/time';
	import { showNew, threadNew, visitSummary, type LabCtx, type TopicView } from '../model';
	import ItemRow from './ItemRow.svelte';
	import ThreadRow from './ThreadRow.svelte';

	let { topic, ctx }: { topic: TopicView; ctx: LabCtx } = $props();
	const feed = $derived(topic.feed);
	const since = $derived(ctx.lastSeen[feed.id]);
	let showMore = $state(false);
</script>

<header>
	<h1>{feed.name}</h1>
	<span class="tag">{feed.mode}</span>
	<span class="dim">{visitSummary(feed, since).toLowerCase()}</span>
</header>

{#if topic.layout}
	<ul class="list">
		{#each topic.layout.live as e (e.id)}
			<li>
				{#if e.kind === 'thread'}
					<ThreadRow thread={e.thread} {ctx} topicId={feed.id} fresh={threadNew(e.thread, since)} />
				{:else}
					<ItemRow item={e.item} {ctx} isNew={showNew(e.item, since)} />
				{/if}
			</li>
		{/each}
		{#if showMore}
			{#each topic.layout.moreItems as item (item.id)}
				<li><ItemRow {item} {ctx} isNew={showNew(item, since)} /></li>
			{/each}
		{/if}
	</ul>
	{#if topic.layout.moreItems.length}
		<button type="button" class="cmd" aria-expanded={showMore} onclick={() => (showMore = !showMore)}>
			{showMore ? '− fewer' : `+ ${topic.layout.moreItems.length} more single stories`}
		</button>
	{/if}

	{#if topic.layout.cooling.length}
		<h2>quiet lately</h2>
		<ul class="list">
			{#each topic.layout.cooling as t (t.id)}
				<li><ThreadRow thread={t} {ctx} topicId={feed.id} fresh={threadNew(t, since)} /></li>
			{/each}
		</ul>
	{/if}

	{#if topic.layout.dormant.length}
		<details class="dormant">
			<summary class="cmd">+ {topic.layout.dormant.length} dormant</summary>
			<ul class="list">
				{#each topic.layout.dormant as t (t.id)}
					<li><ThreadRow thread={t} {ctx} topicId={feed.id} /></li>
				{/each}
			</ul>
		</details>
	{/if}
{:else}
	{#each topic.days as day (day.key)}
		<h2>{dayLabel(day.key, ctx.now).toLowerCase()}</h2>
		<ul class="list">
			{#each [...day.shown, ...day.more] as item (item.id)}
				<li><ItemRow {item} {ctx} isNew={showNew(item, since)} /></li>
			{/each}
		</ul>
	{/each}
{/if}

{#if topic.empty}<p class="dim">nothing in the last few days</p>{/if}

<p class="eof">-- end of {feed.id} · you're all caught up --</p>

<style>
	header {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.25rem 0.75rem;
		margin: 1rem 0 0.5rem;
	}
	h1 {
		margin: 0;
		font-family: var(--cond);
		font-stretch: condensed;
		font-size: 1.9rem;
		line-height: 1.1;
	}
	.tag {
		padding: 0 0.4rem;
		border: 1px solid var(--line);
		font-size: 0.7rem;
		color: var(--teal);
	}
	.dim {
		font-size: 0.8rem;
		color: var(--dim);
	}
	.list {
		list-style: none;
		margin: 0;
		padding: 0;
		border-top: 1px solid var(--line);
	}
	.list li {
		border-bottom: 1px solid var(--line);
	}
	h2 {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		margin: 1.5rem 0 0.25rem;
		font-size: 0.72rem;
		font-weight: 600;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--dim);
	}
	h2::before {
		content: '──';
	}
	.cmd {
		display: inline-flex;
		align-items: center;
		min-height: 44px;
		padding: 0;
		border: 0;
		background: none;
		font: inherit;
		font-size: 0.8rem;
		color: var(--teal);
		cursor: pointer;
	}
	.dormant {
		margin-top: 1rem;
	}
	.dormant summary {
		list-style: none;
	}
	.dormant summary::-webkit-details-marker {
		display: none;
	}
	.eof {
		margin: 2rem 0;
		text-align: center;
		color: var(--dim);
	}
</style>
