<script lang="ts">
	// Owner-only header controls (DESIGN §9.2–9.3). Rendered only on a device with the
	// owner token, so visitors see nothing new.
	import { resolve } from '$app/paths';
	import RefreshButton from './RefreshButton.svelte';
	import { refresher } from '$lib/owner.svelte';
</script>

<div class="owner">
	<RefreshButton />
	<a href={resolve('/settings/')}>Settings</a>
</div>
<p class="status" aria-live="polite">{refresher.status ?? ''}</p>

<style>
	.owner {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	a {
		display: inline-flex;
		align-items: center;
		min-height: 44px;
		padding: 0 0.8rem;
		border: 1px solid var(--border);
		border-radius: var(--radius);
		color: var(--muted);
		font-size: 0.9rem;
		text-decoration: none;
	}
	a:hover {
		color: var(--text);
	}
	.status {
		flex-basis: 100%;
		margin: 0;
		font-size: 0.85rem;
		color: var(--muted);
		text-align: right;
	}
	.status:empty {
		display: none;
	}
</style>
