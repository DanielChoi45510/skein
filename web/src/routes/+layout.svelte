<script lang="ts">
	import '../app.css';
	import { resolve } from '$app/paths';
	import OwnerBar from '$lib/components/OwnerBar.svelte';
	import { owner } from '$lib/owner.svelte';
	import { startOwnerSync, stopOwnerSync } from '$lib/sync.svelte';

	let { children } = $props();

	// Owner read-state sync follows the token (signing in or out on /settings/).
	$effect(() => {
		if (owner.signedIn) startOwnerSync();
		else stopOwnerSync();
	});
</script>

<a class="skip" href="#main">Skip to content</a>
<header>
	<a class="brand" href={resolve('/')}>Skein</a>
	{#if owner.signedIn}<OwnerBar />{/if}
</header>
<main id="main">
	{@render children()}
</main>

<style>
	header {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		max-width: var(--measure);
		margin: 0 auto;
		padding: max(0.75rem, env(safe-area-inset-top)) 1rem 0.25rem;
	}
	.brand {
		display: inline-flex;
		align-items: center;
		min-height: 44px;
		font-weight: 700;
		font-size: 1.15rem;
		letter-spacing: 0.02em;
		text-decoration: none;
		color: var(--accent);
	}
	main {
		max-width: var(--measure);
		margin: 0 auto;
		padding: 0 1rem max(1rem, env(safe-area-inset-bottom));
	}
	.skip {
		position: absolute;
		left: 1rem;
		top: -3rem;
		padding: 0.5rem 0.75rem;
		background: var(--accent);
		color: var(--accent-text);
		border-radius: var(--radius);
		z-index: 1;
	}
	.skip:focus {
		top: 0.5rem;
	}
</style>
