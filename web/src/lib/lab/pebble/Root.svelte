<script lang="ts">
	// Direction C, Pebble: soft and modular. Rounded type, big radii, filled tiles
	// tinted per topic, thumbnails on top, a gentle bento grid.
	import { relativeTime } from '$lib/time';
	import type { DirectionProps } from '../model';
	import Home from './Home.svelte';
	import Spine from './Spine.svelte';
	import Topic from './Topic.svelte';

	let { view, theme, tiles, generatedAt, topic, spine, status, ctx }: DirectionProps = $props();
</script>

<div class="pb" data-theme={theme === 'auto' ? undefined : theme}>
	<header>
		<a class="brand" href={ctx.href({ v: 'home' })}>
			<span class="knot" aria-hidden="true"></span>skein
		</a>
		{#if generatedAt}
			<span class="updated">Updated {relativeTime(generatedAt, ctx.now)}</span>
		{/if}
	</header>
	<main>
		{#if status}
			<p class="status" role="status">{status}</p>
		{:else if view === 'home'}
			<Home {tiles} {ctx} />
		{:else if view === 'topic' && topic}
			<Topic {topic} {tiles} {ctx} />
		{:else if view === 'thread' && spine}
			<Spine {spine} {tiles} {ctx} />
		{/if}
	</main>
</div>

<style>
	.pb {
		/* Tile tints are hsl(var(--h) var(--tile-s) var(--tile-l)); --h is set per topic. */
		--bg: hsl(240 9% 8%);
		--surface: hsl(240 8% 13%);
		--text: hsl(240 10% 95%);
		--dim: hsl(240 6% 68%);
		--tile-s: 30%;
		--tile-l: 17%;
		--pop-s: 75%;
		--pop-l: 74%;
		--chip: hsl(240 8% 22%);
		--shadow: 0 1px 2px rgb(0 0 0 / 0.4), 0 8px 24px rgb(0 0 0 / 0.25);
		--img-filter: saturate(0.8) brightness(0.85);
		--round: ui-rounded, 'SF Pro Rounded', 'Nunito', 'Varela Round', system-ui, -apple-system,
			'Segoe UI', sans-serif;
		color-scheme: dark;
		min-height: 100dvh;
		background: var(--bg);
		color: var(--text);
		font-family: var(--round);
		line-height: 1.45;
	}
	.pb[data-theme='light'] {
		--bg: hsl(36 33% 96%);
		--surface: hsl(0 0% 100%);
		--text: hsl(240 10% 15%);
		--dim: hsl(240 5% 40%);
		--tile-s: 75%;
		--tile-l: 92%;
		--pop-s: 55%;
		--pop-l: 36%;
		--chip: hsl(36 20% 90%);
		--shadow: 0 1px 2px rgb(60 40 20 / 0.06), 0 8px 24px rgb(60 40 20 / 0.08);
		--img-filter: none;
		color-scheme: light;
	}
	@media (prefers-color-scheme: light) {
		.pb:not([data-theme='dark']) {
			--bg: hsl(36 33% 96%);
			--surface: hsl(0 0% 100%);
			--text: hsl(240 10% 15%);
			--dim: hsl(240 5% 40%);
			--tile-s: 75%;
			--tile-l: 92%;
			--pop-s: 55%;
			--pop-l: 36%;
			--chip: hsl(36 20% 90%);
			--shadow: 0 1px 2px rgb(60 40 20 / 0.06), 0 8px 24px rgb(60 40 20 / 0.08);
			--img-filter: none;
			color-scheme: light;
		}
	}
	.pb :global(a) {
		color: inherit;
	}
	header {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		max-width: 70rem;
		margin: 0 auto;
		padding: 0.75rem 1.25rem;
	}
	.brand {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		min-height: 44px;
		font-size: 1.2rem;
		font-weight: 800;
		letter-spacing: -0.01em;
		text-decoration: none;
	}
	.knot {
		width: 1.4rem;
		height: 1.4rem;
		border-radius: 50%;
		background: conic-gradient(
			hsl(205 var(--pop-s) var(--pop-l)),
			hsl(150 var(--pop-s) var(--pop-l)),
			hsl(25 var(--pop-s) var(--pop-l)),
			hsl(280 var(--pop-s) var(--pop-l)),
			hsl(205 var(--pop-s) var(--pop-l))
		);
	}
	.updated {
		padding: 0.3rem 0.75rem;
		border-radius: 999px;
		background: var(--chip);
		font-size: 0.8rem;
		color: var(--dim);
	}
	main {
		max-width: 70rem;
		margin: 0 auto;
		padding: 0 1.25rem max(2rem, env(safe-area-inset-bottom));
	}
	.status {
		margin: 3rem 0;
		text-align: center;
		color: var(--dim);
	}
</style>
