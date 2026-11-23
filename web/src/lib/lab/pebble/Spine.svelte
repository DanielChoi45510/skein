<script lang="ts">
	// Spine and branches as a soft, curving thread: beads for the storyline,
	// side developments hanging off them, related threads as radial spokes.
	import { relativeTime } from '$lib/time';
	import { itemMeta, shortDay, clock, type LabCtx, type Tile } from '../model';
	import type { Spine } from '../spine';
	import { topicHue } from '../thumb';

	let { spine, tiles, ctx }: { spine: Spine; tiles: Tile[]; ctx: LabCtx } = $props();
	const topicName = $derived(tiles.find((t) => t.id === spine.topicId)?.name ?? spine.topicId);
	const updates = $derived(spine.nodes.length + spine.branchCount);
	// Spokes start at 12 o'clock and go round evenly.
	const spokes = $derived(
		spine.related.map((r, i, all) => {
			const a = -Math.PI / 2 + (i * 2 * Math.PI) / all.length;
			return { ...r, x: 50 + 37 * Math.cos(a), y: 50 + 37 * Math.sin(a) };
		})
	);
	const threadHref = (id: string) => ctx.href({ v: 'thread', topic: spine.topicId, thread: id });
</script>

<div class="spine" style:--h={topicHue(spine.topicId)}>
	<header>
		<a class="back" href={ctx.href({ v: 'topic', topic: spine.topicId })}
			><span aria-hidden="true">←</span> {topicName}</a
		>
		<p class="chips">
			<span class="chip story">Story · {updates} updates</span>
			<span class="chip">{spine.state}</span>
			<span class="chip">since {shortDay(spine.createdAt)}</span>
		</p>
		<h1>{spine.title}</h1>
		<p class="mock">Layout mock: the branch structure is invented from the sample thread.</p>
	</header>

	<ol class="flow">
		{#each spine.nodes as node, i (node.item.id)}
			<li class="node" class:right={i % 2 === 1}>
				<div class="rail" aria-hidden="true">
					<svg viewBox="0 0 64 100" preserveAspectRatio="none">
						<path
							d={i % 2 ? 'M32 0 C58 30 6 70 32 100' : 'M32 0 C6 30 58 70 32 100'}
							vector-effect="non-scaling-stroke"
						/>
					</svg>
					<span class="bead"></span>
				</div>
				<div class="cards">
					<article class="main">
						<p class="when">
							{shortDay(node.item.published_at)} · {clock(node.item.published_at)}
						</p>
						<h2>
							<a href={node.item.url} target="_blank" rel="noopener noreferrer">{node.item.title}</a>
						</h2>
						{#if node.item.excerpt}<p class="ex">{node.item.excerpt}</p>{/if}
						<p class="src">{itemMeta(node.item, ctx.sources).source}</p>
					</article>
					{#each node.branches as b (b.id)}
						<article class="branch">
							<p class="when">Side development · {clock(b.published_at)}</p>
							<h3><a href={b.url} target="_blank" rel="noopener noreferrer">{b.title}</a></h3>
							<p class="src">{itemMeta(b, ctx.sources).source}</p>
						</article>
					{/each}
				</div>
			</li>
		{/each}
		<li class="node end" class:right={spine.nodes.length % 2 === 1}>
			<div class="rail" aria-hidden="true"><span class="bead"></span></div>
			<div class="cards"><p class="caught">✓ You're caught up on this story.</p></div>
		</li>
	</ol>

	<section aria-labelledby="pb-related">
		<h2 id="pb-related" class="sec">Related stories</h2>
		{#if spokes.length}
			<div class="radial">
				<svg viewBox="0 0 100 100" aria-hidden="true">
					{#each spokes as s (s.id)}
						<line x1="50" y1="50" x2={s.x} y2={s.y} />
					{/each}
				</svg>
				<div class="hub"><span>{spine.title}</span></div>
				{#each spokes as s (s.id)}
					<a class="spoke" href={threadHref(s.id)} style:left="{s.x}%" style:top="{s.y}%">
						<span class="st">{s.title}</span>
						<span class="sn">{s.itemCount} updates · {s.state}</span>
					</a>
				{/each}
			</div>
			<ul class="strip">
				{#each spokes as s (s.id)}
					<li>
						<a href={threadHref(s.id)}>
							<span class="st">{s.title}</span>
							<span class="sn">{s.itemCount} updates · {relativeTime(s.lastItemAt, ctx.now)}</span>
						</a>
					</li>
				{/each}
			</ul>
		{:else}
			<p class="src">No related stories in {topicName}.</p>
		{/if}
	</section>
</div>

<style>
	header {
		margin: 0.25rem 0 1.5rem;
		padding: 1rem 1.25rem 1.4rem;
		border-radius: 28px;
		background: hsl(var(--h) var(--tile-s) var(--tile-l));
	}
	.back {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		min-height: 44px;
		padding: 0 0.9rem;
		border-radius: 999px;
		background: var(--surface);
		font-size: 0.88rem;
		font-weight: 700;
		text-decoration: none;
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
		margin: 0.9rem 0 0;
	}
	.chip {
		padding: 0.1rem 0.6rem;
		border-radius: 999px;
		background: var(--surface);
		font-size: 0.75rem;
		font-weight: 700;
		color: var(--dim);
	}
	.chip.story {
		color: hsl(var(--h) var(--pop-s) var(--pop-l));
	}
	h1 {
		margin: 0.4rem 0 0;
		font-size: clamp(1.8rem, 6vw, 2.8rem);
		font-weight: 800;
		line-height: 1.1;
		letter-spacing: -0.02em;
	}
	.mock {
		margin: 0.5rem 0 0;
		font-size: 0.78rem;
		color: var(--dim);
	}

	/* The flow: phone = rail on the left; laptop = rail in the middle, cards alternate. */
	.flow {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.node {
		display: grid;
		grid-template-columns: 2.75rem minmax(0, 1fr);
		grid-template-areas: 'rail cards';
		column-gap: 0.5rem;
		padding-bottom: 1.25rem;
	}
	@media (min-width: 52rem) {
		.node {
			grid-template-columns: minmax(0, 1fr) 4rem minmax(0, 1fr);
			grid-template-areas: 'cards rail .';
		}
		.node.right {
			grid-template-areas: '. rail cards';
		}
	}
	.rail {
		grid-area: rail;
		position: relative;
	}
	.rail svg {
		position: absolute;
		left: 0;
		top: 1.6rem;
		width: 100%;
		height: calc(100% + 1.25rem);
		overflow: visible;
	}
	.rail path {
		fill: none;
		stroke: hsl(var(--h) var(--pop-s) var(--pop-l));
		stroke-width: 4;
		stroke-linecap: round;
		opacity: 0.7;
	}
	.bead {
		position: absolute;
		left: 50%;
		top: 1.6rem;
		width: 18px;
		height: 18px;
		border-radius: 50%;
		transform: translate(-50%, -50%);
		background: hsl(var(--h) var(--pop-s) var(--pop-l));
		box-shadow: 0 0 0 5px var(--bg);
	}
	.end .bead {
		background: var(--bg);
		border: 4px solid hsl(var(--h) var(--pop-s) var(--pop-l));
	}
	.cards {
		grid-area: cards;
		min-width: 0;
	}
	article.main {
		padding: 0.9rem 1.1rem 1rem;
		border-radius: 22px;
		background: var(--surface);
		box-shadow: var(--shadow);
	}
	.when {
		margin: 0;
		font-size: 0.75rem;
		font-weight: 700;
		color: hsl(var(--h) var(--pop-s) var(--pop-l));
	}
	.flow h2 {
		margin: 0.25rem 0 0;
		font-size: 1.12rem;
		font-weight: 700;
		line-height: 1.3;
	}
	.flow h2 a,
	h3 a {
		display: block;
		min-height: 44px;
		text-decoration: none;
	}
	.flow h2 a:hover,
	h3 a:hover {
		text-decoration: underline;
	}
	.ex {
		display: -webkit-box;
		margin: 0;
		overflow: hidden;
		-webkit-line-clamp: 3;
		line-clamp: 3;
		-webkit-box-orient: vertical;
		font-size: 0.92rem;
		color: var(--dim);
	}
	.src {
		margin: 0.4rem 0 0;
		font-size: 0.78rem;
		color: var(--dim);
	}
	article.branch {
		position: relative;
		margin: 0.75rem 0 0 2rem;
		padding: 0.7rem 1rem 0.8rem;
		border-radius: 18px;
		background: hsl(var(--h) var(--tile-s) var(--tile-l));
	}
	article.branch::before {
		content: '';
		position: absolute;
		left: -1.4rem;
		top: -0.75rem;
		width: 1.4rem;
		height: 2rem;
		border-left: 3px solid hsl(var(--h) var(--pop-s) var(--pop-l));
		border-bottom: 3px solid hsl(var(--h) var(--pop-s) var(--pop-l));
		border-bottom-left-radius: 14px;
		opacity: 0.7;
	}
	h3 {
		margin: 0.15rem 0 0;
		font-size: 1rem;
		font-weight: 700;
		line-height: 1.3;
	}
	.caught {
		margin: 1.1rem 0 0;
		color: var(--dim);
		font-weight: 600;
	}

	/* Related threads: radial on wide screens, a scroll strip on phones. */
	section {
		margin-top: 2.5rem;
	}
	.sec {
		margin: 0 0 1rem;
		font-size: 1.15rem;
		font-weight: 800;
	}
	.radial {
		display: none;
		position: relative;
		width: min(100%, 30rem);
		aspect-ratio: 1;
		margin: 0 auto;
	}
	.radial svg {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
	}
	.radial line {
		stroke: hsl(var(--h) var(--pop-s) var(--pop-l));
		stroke-width: 0.6;
		stroke-dasharray: 1.5 1.5;
		opacity: 0.7;
	}
	.hub {
		position: absolute;
		left: 50%;
		top: 50%;
		display: grid;
		place-items: center;
		width: 9rem;
		height: 9rem;
		padding: 1rem;
		border-radius: 50%;
		transform: translate(-50%, -50%);
		background: hsl(var(--h) var(--tile-s) var(--tile-l));
		box-shadow: var(--shadow);
		text-align: center;
		font-weight: 800;
		line-height: 1.2;
	}
	.hub span {
		display: -webkit-box;
		overflow: hidden;
		-webkit-line-clamp: 4;
		line-clamp: 4;
		-webkit-box-orient: vertical;
	}
	.spoke {
		position: absolute;
		display: flex;
		flex-direction: column;
		width: 10rem;
		padding: 0.6rem 0.8rem;
		border-radius: 18px;
		transform: translate(-50%, -50%);
		background: var(--surface);
		box-shadow: var(--shadow);
		text-decoration: none;
	}
	.spoke:hover .st,
	.strip a:hover .st {
		text-decoration: underline;
	}
	.st {
		font-weight: 700;
		line-height: 1.25;
	}
	.sn {
		font-size: 0.75rem;
		color: var(--dim);
	}
	.strip {
		display: flex;
		gap: 0.75rem;
		overflow-x: auto;
		list-style: none;
		margin: 0;
		padding: 0 0 0.75rem;
		scroll-snap-type: x mandatory;
	}
	.strip li {
		flex: 0 0 75%;
		scroll-snap-align: start;
	}
	.strip a {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
		height: 100%;
		min-height: 44px;
		padding: 0.8rem 1rem;
		border-radius: 18px;
		background: hsl(var(--h) var(--tile-s) var(--tile-l));
		text-decoration: none;
	}
	/* After .strip's own rules, so it wins. */
	@media (min-width: 40rem) {
		.radial {
			display: block;
		}
		.strip {
			display: none;
		}
	}
</style>
