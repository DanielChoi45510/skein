<script lang="ts">
	import ItemCard from './ItemCard.svelte';
	import type { LocalDay } from '$lib/group';
	import type { ExportItem, SourceSummary } from '$lib/types';
	import { dayLabel } from '$lib/time';

	interface Props {
		days: LocalDay[];
		sources: Map<string, SourceSummary>;
		isNew: (item: ExportItem) => boolean;
		now: number;
	}
	let { days, sources, isNew, now }: Props = $props();

	// "+N more" per day, collapsed by default.
	let expanded = $state<Record<string, boolean>>({});
</script>

{#each days as day (day.key)}
	<section aria-labelledby="day-{day.key}">
		<h2 id="day-{day.key}">{dayLabel(day.key, now)}</h2>
		<ul>
			{#each day.shown as item (item.id)}
				<li><ItemCard {item} {sources} isNew={isNew(item)} {now} /></li>
			{/each}
			{#if expanded[day.key]}
				{#each day.more as item (item.id)}
					<li><ItemCard {item} {sources} isNew={isNew(item)} {now} /></li>
				{/each}
			{/if}
		</ul>
		{#if day.more.length}
			<button
				type="button"
				class="more"
				aria-expanded={expanded[day.key] ?? false}
				onclick={() => (expanded[day.key] = !expanded[day.key])}
			>
				{expanded[day.key] ? 'Show fewer' : `+${day.more.length} more`}
			</button>
		{/if}
	</section>
{/each}

<style>
	section {
		margin-top: 1.75rem;
	}
	h2 {
		margin: 0 0 0.6rem;
		font-size: 0.85rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--muted);
	}
	ul {
		display: grid;
		gap: 0.6rem;
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.more {
		display: block;
		width: 100%;
		min-height: 44px;
		margin-top: 0.6rem;
		border: 1px dashed var(--border);
		border-radius: var(--radius);
		background: transparent;
		color: var(--muted);
		cursor: pointer;
	}
	.more:hover {
		color: var(--text);
	}
</style>
