<script lang="ts">
	import { onDestroy } from 'svelte';
	import { waitLabel } from '$lib/owner';
	import { refresher } from '$lib/owner.svelte';

	let now = $state(Date.now());
	const timer = setInterval(() => (now = Date.now()), 5000);
	onDestroy(() => clearInterval(timer));
	const wait = $derived(waitLabel(refresher.until, now));
</script>

<button
	type="button"
	onclick={() => refresher.refresh().then(() => (now = Date.now()))}
	disabled={refresher.sending || wait !== null}
>
	{refresher.sending ? 'Starting…' : (wait ?? 'Refresh now')}
</button>

<style>
	button {
		display: inline-flex;
		align-items: center;
		min-height: 44px;
		padding: 0 0.8rem;
		border: 1px solid var(--border);
		border-radius: var(--radius);
		background: transparent;
		color: var(--muted);
		font-size: 0.9rem;
		cursor: pointer;
	}
	button:hover:not(:disabled) {
		color: var(--text);
	}
	button:disabled {
		cursor: default;
		opacity: 0.7;
	}
</style>
