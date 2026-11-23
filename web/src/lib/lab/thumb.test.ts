import { describe, expect, it } from 'vitest';
import { hasThumb, thumb, topicHue } from './thumb';

const ids = Array.from({ length: 300 }, (_, i) => `item-${i}`);

describe('placeholder thumbnails', () => {
	it('are deterministic inline SVGs, different per style', () => {
		const id = ids.find(hasThumb)!;
		const a = thumb(id, 'duotone');
		expect(a).toBe(thumb(id, 'duotone'));
		expect(a?.startsWith('data:image/svg+xml,')).toBe(true);
		expect(thumb(id, 'pixel')).not.toBe(a);
		expect(thumb(id, 'blob')).not.toBe(a);
	});

	it('leave roughly a third of items without an image', () => {
		const none = ids.filter((id) => thumb(id, 'blob') === null).length / ids.length;
		expect(none).toBeGreaterThan(0.2);
		expect(none).toBeLessThan(0.45);
	});

	it('never reference anything outside the data URI', () => {
		for (const id of ids.slice(0, 30)) {
			for (const style of ['duotone', 'pixel', 'blob'] as const) {
				const svg = decodeURIComponent(thumb(id, style)?.slice(19) ?? '');
				expect(svg).not.toMatch(/https?:\/\/(?!www\.w3\.org\/2000\/svg)/);
			}
		}
	});

	it('give each topic a stable hue', () => {
		expect(topicHue('world')).toBe(topicHue('world'));
		expect(topicHue('world')).toBeGreaterThanOrEqual(0);
		expect(topicHue('world')).toBeLessThan(360);
	});
});
