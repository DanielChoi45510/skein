import { describe, expect, it } from 'vitest';
import { FixedWindow } from '../src/limiter';

describe('FixedWindow', () => {
	it('allows `limit` hits per window, then refuses until it resets', () => {
		let t = 0;
		const w = new FixedWindow({ limit: 2, periodMs: 1000 }, () => t);
		expect([w.hit('a'), w.hit('a'), w.hit('a')]).toEqual([true, true, false]);
		expect(w.blocked('a')).toBe(true);
		expect(w.hit('b')).toBe(true); // per key
		t = 1000;
		expect(w.blocked('a')).toBe(false);
		expect(w.hit('a')).toBe(true);
	});

	it('blocked() does not count a hit', () => {
		const w = new FixedWindow({ limit: 1, periodMs: 1000 }, () => 0);
		expect(w.blocked('a')).toBe(false);
		expect(w.blocked('a')).toBe(false);
		expect(w.hit('a')).toBe(true);
		expect(w.blocked('a')).toBe(true);
	});
});
