// Placeholder thumbnails for the design lab. The export has no image field yet,
// so a hash of the item id picks a deterministic inline SVG: no image hosts, no
// network, no tracking. About a third of items get none, so the no-image card
// layout is visible too.

export type ThumbStyle = 'duotone' | 'pixel' | 'blob';

/** FNV-1a, 32-bit. */
export function hash(s: string): number {
	let h = 0x811c9dc5;
	for (let i = 0; i < s.length; i++) {
		h ^= s.charCodeAt(i);
		h = Math.imul(h, 0x01000193);
	}
	return h >>> 0;
}

/** mulberry32: a tiny seeded PRNG in [0, 1). */
function rng(seed: number): () => number {
	let a = seed;
	return () => {
		a = (a + 0x6d2b79f5) | 0;
		let t = Math.imul(a ^ (a >>> 15), 1 | a);
		t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
}

export const hasThumb = (id: string) => hash(id) % 3 !== 0;

// Calm, distinguishable hues for per-topic tints (Pebble).
const TOPIC_HUES = [205, 150, 25, 280, 340, 95, 50, 240];
export const topicHue = (id: string) => TOPIC_HUES[hash(id) % TOPIC_HUES.length];

const uri = (svg: string) => `data:image/svg+xml,${encodeURIComponent(svg)}`;
const r1 = (n: number) => Math.round(n * 10) / 10;

/** Newsprint halftone: dots that grow toward a focal point, in two inks (16:9). */
function duotone(rand: () => number): string {
	const hue = Math.floor(rand() * 360);
	const fx = rand() * 160;
	const fy = rand() * 90;
	const dots: string[] = [];
	for (let y = 5; y < 90; y += 10) {
		for (let x = 5; x < 160; x += 10) {
			const d = Math.hypot(x - fx, y - fy) / 120;
			const r = Math.max(0.6, 4.6 * (1 - d));
			dots.push(`<circle cx="${x}" cy="${y}" r="${r1(r)}"/>`);
		}
	}
	return (
		`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 90">` +
		`<rect width="160" height="90" fill="hsl(${hue} 18% 86%)"/>` +
		`<g fill="hsl(${hue} 30% 24%)">${dots.join('')}</g></svg>`
	);
}

/** Mirrored 8×8 pixel block, graphite and teal (1:1). */
function pixel(rand: () => number): string {
	const shades = ['#1d2326', '#2b3a3c', '#3f6f6a', '#69b3a7', '#c9a24a'];
	const cells: string[] = [];
	for (let y = 0; y < 8; y++) {
		for (let x = 0; x < 4; x++) {
			const v = rand();
			const fill = shades[v < 0.35 ? 0 : v < 0.6 ? 1 : v < 0.82 ? 2 : v < 0.96 ? 3 : 4];
			cells.push(`<rect x="${x}" y="${y}" width="1" height="1" fill="${fill}"/>`);
			cells.push(`<rect x="${7 - x}" y="${y}" width="1" height="1" fill="${fill}"/>`);
		}
	}
	return (
		`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8" shape-rendering="crispEdges">` +
		`${cells.join('')}</svg>`
	);
}

/** Soft pastel blobs (4:3). */
function blob(rand: () => number): string {
	const base = Math.floor(rand() * 360);
	const circles: string[] = [];
	for (let i = 0; i < 3; i++) {
		const hue = (base + i * 50 + Math.floor(rand() * 30)) % 360;
		const cx = r1(20 + rand() * 120);
		const cy = r1(15 + rand() * 90);
		const r = r1(28 + rand() * 30);
		circles.push(`<circle cx="${cx}" cy="${cy}" r="${r}" fill="hsl(${hue} 75% 72%)"/>`);
	}
	return (
		`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 120">` +
		`<defs><filter id="b" x="-50%" y="-50%" width="200%" height="200%">` +
		`<feGaussianBlur stdDeviation="14"/></filter></defs>` +
		`<rect width="160" height="120" fill="hsl(${base} 60% 90%)"/>` +
		`<g filter="url(#b)">${circles.join('')}</g></svg>`
	);
}

const DRAW: Record<ThumbStyle, (rand: () => number) => string> = { duotone, pixel, blob };

/** A placeholder image as a data URI, or null for items that get none. */
export function thumb(id: string, style: ThumbStyle): string | null {
	if (!hasThumb(id)) return null;
	return uri(DRAW[style](rng(hash(`${style}:${id}`))));
}
