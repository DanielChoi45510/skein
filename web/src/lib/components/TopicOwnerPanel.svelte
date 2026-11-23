<script lang="ts">
	// Owner tools on a topic page (DESIGN §9.2, §10.2): unmute threads, and move single
	// stories (pending or unthreaded) into a thread.
	import RefreshButton from './RefreshButton.svelte';
	import { moveItems, postOverride } from '$lib/overridesClient';
	import { owner } from '$lib/owner.svelte';
	import type { TopicFeed } from '$lib/types';

	interface Props {
		feed: TopicFeed;
		selecting: boolean;
		selected: string[];
		onClearSelection: () => void;
	}
	let { feed, selecting = $bindable(), selected, onClearSelection }: Props = $props();

	let moveTo = $state('');
	let busy = $state(false);
	let saved = $state<string | null>(null);
	let problem = $state<string | null>(null);
	let unmuted = $state<string[]>([]); // pending until the next update

	const call = (path: string, init?: RequestInit) => owner.call(path, init);
	const muted = $derived((feed.muted ?? []).filter((m) => !unmuted.includes(m.id)));
	const targetTitle = (id: string) => feed.threads.find((t) => t.id === id)?.title ?? id;

	async function run(work: () => Promise<unknown>, done: string): Promise<boolean> {
		busy = true;
		problem = null;
		saved = null;
		try {
			await work();
			saved = `${done} It takes effect on the next update.`;
			return true;
		} catch (e) {
			problem = e instanceof Error ? e.message : 'Saving failed.';
			return false;
		} finally {
			busy = false;
		}
	}

	async function unmute(id: string, title: string) {
		if (await run(() => postOverride(call, { action: 'unmute', thread: id }), `Unmuted “${title}”.`)) {
			unmuted = [...unmuted, id];
		}
	}

	async function move() {
		const items = [...selected];
		const n = `${items.length} ${items.length === 1 ? 'story' : 'stories'}`;
		if (await run(() => moveItems(call, items, moveTo), `Moving ${n} to “${targetTitle(moveTo)}”.`)) {
			onClearSelection();
		}
	}
</script>

<details class="owner-panel">
	<summary>Owner tools{muted.length ? ` · ${muted.length} muted` : ''}</summary>

	{#if feed.threads.length}
		<div class="row">
			<button type="button" class="quiet" onclick={() => (selecting = !selecting)}>
				{selecting ? 'Done selecting' : 'Select single stories…'}
			</button>
		</div>
		{#if selecting}
			<div class="row" aria-live="polite">
				<label for="topic-move-to">Move {selected.length} selected to</label>
				<select id="topic-move-to" bind:value={moveTo}>
					<option value="" disabled>Choose a thread…</option>
					{#each feed.threads as t (t.id)}<option value={t.id}>{t.title}</option>{/each}
				</select>
				<button type="button" disabled={busy || !selected.length || !moveTo} onclick={move}>Move</button>
			</div>
		{/if}
	{/if}

	{#if muted.length}
		<h2>Muted ({muted.length})</h2>
		<ul>
			{#each muted as m (m.id)}
				<li>
					<span>{m.title}</span>
					<button type="button" disabled={busy} onclick={() => unmute(m.id, m.title)}>Unmute</button>
				</li>
			{/each}
		</ul>
	{/if}

	<div class="feedback" aria-live="polite">
		{#if problem}<p class="problem">{problem}</p>{/if}
		{#if saved}
			<p>{saved}</p>
			<RefreshButton />
		{/if}
	</div>
</details>

<style>
	.owner-panel {
		margin-top: 1rem;
		padding: 0.25rem 1rem 0.75rem;
		border: 1px dashed var(--border);
		border-radius: var(--radius);
	}
	summary {
		min-height: 44px;
		display: flex;
		align-items: center;
		color: var(--muted);
		cursor: pointer;
	}
	h2 {
		margin: 1rem 0 0.4rem;
		font-size: 0.85rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--muted);
	}
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	li {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		padding: 0.25rem 0;
	}
	.row {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		margin-top: 0.75rem;
	}
	label {
		flex-basis: 100%;
		font-size: 0.85rem;
		color: var(--muted);
	}
	select {
		flex: 1 1 14rem;
		min-width: 0; /* long thread titles in options must not widen the panel */
		max-width: 100%;
		min-height: 44px;
		padding: 0 0.6rem;
		border: 1px solid var(--border);
		border-radius: var(--radius);
		background: var(--bg);
		color: var(--text);
		font: inherit;
	}
	button {
		min-height: 44px;
		padding: 0 0.9rem;
		border: 1px solid var(--border);
		border-radius: var(--radius);
		background: var(--surface);
		color: var(--text);
		cursor: pointer;
	}
	button.quiet {
		background: transparent;
		color: var(--muted);
	}
	button:disabled {
		opacity: 0.6;
		cursor: default;
	}
	.feedback {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem 1rem;
	}
	.feedback p {
		margin: 0.5rem 0 0;
		font-size: 0.9rem;
	}
	.problem {
		color: var(--accent);
	}
</style>
