<script lang="ts">
	// Direction A, Broadsheet: editorial. Serif headlines, hairline rules instead
	// of boxes, newsprint and ink, one deep red accent, airy.
	import { relativeTime } from '$lib/time';
	import { longDate, type DirectionProps } from '../model';
	import Home from './Home.svelte';
	import Spine from './Spine.svelte';
	import Topic from './Topic.svelte';

	let { view, theme, tiles, generatedAt, topic, spine, status, ctx }: DirectionProps = $props();
</script>

<div class="bs" data-theme={theme === 'auto' ? undefined : theme}>
	<header class:compact={view !== 'home'}>
		<a class="title" href={ctx.href({ v: 'home' })}>Skein</a>
		{#if generatedAt}
			<p class="dateline">
				<span>{longDate(generatedAt)}</span>
				<span aria-hidden="true">·</span>
				<span>Edition updated {relativeTime(generatedAt, ctx.now)}</span>
			</p>
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
	.bs {
		--paper: #15140f;
		--ink: #ece6d8;
		--ink-2: #b9b1a0;
		--rule: #3a372e;
		--rule-strong: #d9d1bf;
		--red: #e0705e;
		--img-filter: brightness(0.62) sepia(0.25);
		--serif: 'Iowan Old Style', 'Charter', 'Bitstream Charter', 'Sitka Text', Cambria, Georgia,
			serif;
		--sans: system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
		color-scheme: dark;
		min-height: 100dvh;
		background: var(--paper);
		color: var(--ink);
		font-family: var(--sans);
		line-height: 1.5;
	}
	.bs[data-theme='light'] {
		--paper: #f6f1e7;
		--ink: #1d1b16;
		--ink-2: #5d574b;
		--rule: #d6cfbf;
		--rule-strong: #1d1b16;
		--red: #a3261b;
		--img-filter: none;
		color-scheme: light;
	}
	@media (prefers-color-scheme: light) {
		.bs:not([data-theme='dark']) {
			--paper: #f6f1e7;
			--ink: #1d1b16;
			--ink-2: #5d574b;
			--rule: #d6cfbf;
			--rule-strong: #1d1b16;
			--red: #a3261b;
			--img-filter: none;
			color-scheme: light;
		}
	}
	.bs :global(a) {
		color: inherit;
	}
	header {
		max-width: 72rem;
		margin: 0 auto;
		padding: 1.75rem 1.25rem 0.6rem;
		text-align: center;
		border-bottom: 3px double var(--rule-strong);
	}
	.title {
		font-family: var(--serif);
		font-size: clamp(2.6rem, 9vw, 4.25rem);
		font-weight: 700;
		line-height: 1;
		letter-spacing: -0.02em;
		text-decoration: none;
	}
	header.compact {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		justify-content: space-between;
		gap: 0.25rem 1rem;
		padding-top: 1rem;
		text-align: left;
	}
	header.compact .title {
		font-size: 1.9rem;
	}
	.dateline {
		display: flex;
		flex-wrap: wrap;
		justify-content: center;
		gap: 0 0.5rem;
		margin: 0.6rem 0 0;
		font-size: 0.72rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--ink-2);
	}
	.compact .dateline {
		justify-content: flex-start;
		margin: 0;
	}
	main {
		max-width: 72rem;
		margin: 0 auto;
		padding: 0 1.25rem max(2rem, env(safe-area-inset-bottom));
	}
	.status {
		margin: 3rem 0;
		text-align: center;
		font-family: var(--serif);
		font-style: italic;
		color: var(--ink-2);
	}
</style>
