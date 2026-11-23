<script lang="ts">
	// Direction B, Ledger: dense and technical. Monospace meta and counters,
	// condensed headlines, flat outlined cells, graphite with one teal accent.
	import { age, type DirectionProps } from '../model';
	import Home from './Home.svelte';
	import Spine from './Spine.svelte';
	import Topic from './Topic.svelte';

	let { view, theme, tiles, generatedAt, topic, spine, status, ctx }: DirectionProps = $props();
	const path = $derived(
		view === 'home'
			? '~'
			: view === 'topic'
				? `~/${topic?.feed.id ?? ''}`
				: `~/${spine?.topicId ?? ''}/${spine?.id.slice(0, 7) ?? ''}`
	);
</script>

<div class="lg" data-theme={theme === 'auto' ? undefined : theme}>
	<header>
		<a class="brand" href={ctx.href({ v: 'home' })}>skein</a>
		<span class="path">{path}</span>
		{#if generatedAt}
			<span class="gen" title={generatedAt}>built {age(generatedAt, ctx.now)} ago</span>
		{/if}
	</header>
	<main>
		{#if status}
			<p class="status" role="status">{status}</p>
		{:else if view === 'home'}
			<Home {tiles} {ctx} />
		{:else if view === 'topic' && topic}
			<Topic {topic} {ctx} />
		{:else if view === 'thread' && spine}
			<Spine {spine} {ctx} />
		{/if}
	</main>
</div>

<style>
	.lg {
		--bg: #0d1012;
		--panel: #13181b;
		--line: #263036;
		--text: #d6dcdf;
		--dim: #85929a;
		--teal: #5fb8aa;
		--amber: #e0aa4c;
		--mono: ui-monospace, 'SF Mono', SFMono-Regular, Menlo, 'Cascadia Mono', Consolas, monospace;
		--cond: 'Avenir Next Condensed', 'Roboto Condensed', 'Arial Narrow', system-ui, sans-serif;
		color-scheme: dark;
		min-height: 100dvh;
		background: var(--bg);
		color: var(--text);
		font: 0.9rem/1.45 var(--mono);
	}
	.lg[data-theme='light'] {
		--bg: #f3f4f1;
		--panel: #ffffff;
		--line: #d2d7d3;
		--text: #14181a;
		--dim: #59646a;
		--teal: #17695e;
		--amber: #8c5d00;
		color-scheme: light;
	}
	@media (prefers-color-scheme: light) {
		.lg:not([data-theme='dark']) {
			--bg: #f3f4f1;
			--panel: #ffffff;
			--line: #d2d7d3;
			--text: #14181a;
			--dim: #59646a;
			--teal: #17695e;
			--amber: #8c5d00;
			color-scheme: light;
		}
	}
	.lg :global(a) {
		color: inherit;
	}
	header {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0 1rem;
		max-width: 64rem;
		margin: 0 auto;
		padding: 0.5rem 1rem;
		border-bottom: 1px solid var(--line);
	}
	.brand {
		display: inline-flex;
		align-items: center;
		min-height: 44px;
		font-weight: 700;
		color: var(--teal);
		text-decoration: none;
	}
	.brand::before {
		content: '▍';
		margin-right: 0.3rem;
	}
	.path {
		color: var(--dim);
	}
	.gen {
		margin-left: auto;
		font-size: 0.75rem;
		color: var(--dim);
	}
	main {
		max-width: 64rem;
		margin: 0 auto;
		padding: 0 1rem max(2rem, env(safe-area-inset-bottom));
	}
	.status {
		margin: 2rem 0;
		color: var(--dim);
	}
	.status::before {
		content: '$ ';
		color: var(--teal);
	}
</style>
