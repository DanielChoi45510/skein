<script lang="ts">
	import '../app.css';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';

	let { children } = $props();
	// The design lab (/lab/) draws its own full-width chrome.
	const bare = $derived(page.route.id?.startsWith('/lab') ?? false);
</script>

{#if bare}
	{@render children()}
{:else}
	<a class="skip" href="#main">Skip to content</a>
	<header>
		<a class="brand" href={resolve('/')}>Skein</a>
	</header>
	<main id="main">
		{@render children()}
	</main>
{/if}

<style>
	header {
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
