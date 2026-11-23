<script lang="ts">
	// Owner tools on a thread page (DESIGN §9.2, §10.2). Every change is an override
	// stored by the Worker; the pipeline applies it on its next run.
	import { onMount } from 'svelte';
	import RefreshButton from './RefreshButton.svelte';
	import {
		cleanTitle,
		getOverrides,
		moveItems,
		postOverride,
		splitThread,
		MAX_TITLE,
		type OverrideAction,
		type ThreadSettings
	} from '$lib/overridesClient';
	import { owner } from '$lib/owner.svelte';
	import type { ThreadFeed, ThreadSummary } from '$lib/types';

	interface Props {
		thread: ThreadFeed;
		targets: ThreadSummary[]; // other listed threads in the topic (merge / move)
		selecting: boolean;
		selected: string[];
		onClearSelection: () => void;
	}
	let { thread, targets, selecting = $bindable(), selected, onClearSelection }: Props = $props();

	let settings = $state<ThreadSettings>({});
	let title = $state('');
	let mergeInto = $state('');
	let confirmMerge = $state(false);
	let moveTo = $state('');
	let splitTitle = $state('');
	let busy = $state(false);
	let saved = $state<string | null>(null);
	let problem = $state<string | null>(null);

	const call = (path: string, init?: RequestInit) => owner.call(path, init);
	const predefined = $derived(thread.kind === 'tracker' || thread.kind === 'fixed');
	const targetTitle = (id: string) => targets.find((t) => t.id === id)?.title ?? id;

	onMount(async () => {
		title = thread.title;
		try {
			settings = (await getOverrides(call)).threads[thread.id] ?? {};
			// A rename saved since the last update isn't in the feed yet: show it.
			if (settings.title) title = settings.title;
		} catch {
			// shown as defaults; saving still works
		}
	});

	async function run(work: () => Promise<unknown>, done: string) {
		busy = true;
		problem = null;
		saved = null;
		try {
			const doc = (await work()) as { threads: Record<string, ThreadSettings> } | undefined;
			if (doc?.threads) settings = doc.threads[thread.id] ?? {};
			saved = `${done} It takes effect on the next update.`;
		} catch (e) {
			problem = e instanceof Error ? e.message : 'Saving failed.';
		}
		busy = false;
	}

	const send = (action: OverrideAction, done: string) =>
		run(() => postOverride(call, action), done);

	function rename(event: SubmitEvent) {
		event.preventDefault();
		const t = cleanTitle(title);
		send({ action: 'rename', thread: thread.id, title: t }, t ? 'Renamed.' : 'Back to the automatic title.');
	}

	function merge() {
		if (!confirmMerge) {
			confirmMerge = true;
			return;
		}
		confirmMerge = false;
		send(
			{ action: 'merge', from: thread.id, into: mergeInto },
			`Merging into “${targetTitle(mergeInto)}”.`
		);
	}

	async function split() {
		const items = [...selected];
		await run(
			() => splitThread(call, thread.id, items, cleanTitle(splitTitle)),
			`Splitting ${items.length} ${items.length === 1 ? 'story' : 'stories'} into a new thread.`
		);
		if (!problem) {
			splitTitle = '';
			onClearSelection();
		}
	}

	async function move() {
		const items = [...selected];
		await run(
			() => moveItems(call, items, moveTo),
			`Moving ${items.length} ${items.length === 1 ? 'story' : 'stories'} to “${targetTitle(moveTo)}”.`
		);
		if (!problem) onClearSelection();
	}
</script>

<details class="owner-panel">
	<summary>Owner tools</summary>

	{#if !predefined}
		<form class="row" onsubmit={rename}>
			<label for="thread-title">Title</label>
			<input id="thread-title" maxlength={MAX_TITLE} bind:value={title} />
			<button type="submit" disabled={busy}>Rename</button>
			{#if settings.title}
				<button
					type="button"
					class="quiet"
					disabled={busy}
					onclick={() => send({ action: 'rename', thread: thread.id, title: null }, 'Back to the automatic title.')}
				>
					Use automatic title
				</button>
			{/if}
		</form>
	{/if}

	<div class="row">
		<button
			type="button"
			disabled={busy}
			onclick={() =>
				send(
					{ action: settings.pinned ? 'unpin' : 'pin', thread: thread.id },
					settings.pinned ? 'Unpinned.' : 'Pinned to the top of the topic.'
				)}
		>
			{settings.pinned ? 'Unpin' : 'Pin'}
		</button>
		<button
			type="button"
			disabled={busy}
			onclick={() =>
				send(
					{ action: settings.muted ? 'unmute' : 'mute', thread: thread.id },
					settings.muted
						? 'Unmuted.'
						: 'Muted: hidden for everyone; unmute from the topic page.'
				)}
		>
			{settings.muted ? 'Unmute' : 'Mute'}
		</button>
		<button type="button" class="quiet" onclick={() => (selecting = !selecting)}>
			{selecting ? 'Done selecting' : 'Select stories…'}
		</button>
	</div>

	{#if !predefined && targets.length}
		<div class="row">
			<label for="merge-into">Merge this thread into</label>
			<select id="merge-into" bind:value={mergeInto} onchange={() => (confirmMerge = false)}>
				<option value="" disabled>Choose a thread…</option>
				{#each targets as t (t.id)}<option value={t.id}>{t.title}</option>{/each}
			</select>
			<button type="button" class:danger={confirmMerge} disabled={busy || !mergeInto} onclick={merge}>
				{confirmMerge ? 'Confirm merge' : 'Merge'}
			</button>
		</div>
		{#if confirmMerge}
			<p class="hint">
				All of this thread's stories join “{targetTitle(mergeInto)}”, and this thread goes away.
			</p>
		{/if}
	{/if}

	{#if selecting}
		<div class="selection" aria-live="polite">
			<p>{selected.length} selected</p>
			{#if !predefined}
				<div class="row">
					<label for="split-title">New thread title (optional)</label>
					<input id="split-title" maxlength={MAX_TITLE} bind:value={splitTitle} />
					<button type="button" disabled={busy || !selected.length} onclick={split}>Split into new thread</button>
				</div>
			{/if}
			{#if targets.length}
				<div class="row">
					<label for="move-to">Move to</label>
					<select id="move-to" bind:value={moveTo}>
						<option value="" disabled>Choose a thread…</option>
						{#each targets as t (t.id)}<option value={t.id}>{t.title}</option>{/each}
					</select>
					<button type="button" disabled={busy || !selected.length || !moveTo} onclick={move}>Move</button>
				</div>
			{/if}
		</div>
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
	input,
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
	button.danger {
		border-color: var(--accent);
		color: var(--accent);
	}
	button:disabled {
		opacity: 0.6;
		cursor: default;
	}
	.selection {
		margin-top: 0.75rem;
		padding-top: 0.5rem;
		border-top: 1px solid var(--border);
	}
	.selection p {
		margin: 0;
		font-weight: 600;
	}
	.hint,
	.feedback p {
		margin: 0.5rem 0 0;
		font-size: 0.9rem;
	}
	.feedback {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem 1rem;
	}
	.problem {
		color: var(--accent);
	}
</style>
