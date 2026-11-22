import { describe, expect, it } from 'vitest';
import { isNew, latestFirstSeen, loadLastSeen, markSeen, newCount } from './readState';
import type { ExportItem } from './types';

function memoryStore(initial: Record<string, string> = {}) {
	const data = new Map(Object.entries(initial));
	return {
		data,
		getItem: (k: string) => data.get(k) ?? null,
		setItem: (k: string, v: string) => void data.set(k, v)
	};
}

function item(first_seen_at: string, collapsed = false): ExportItem {
	return {
		id: first_seen_at,
		title: 't',
		url: 'https://example.com',
		source_id: 's',
		published_at: first_seen_at,
		first_seen_at,
		excerpt: null,
		importance: 0.5,
		also_covered_by: [],
		collapsed
	};
}

describe('read state', () => {
	it('round-trips and never moves backwards', () => {
		const store = memoryStore();
		markSeen('world', '2026-11-21T12:00:00Z', store);
		markSeen('world', '2026-11-21T11:00:00Z', store);
		expect(loadLastSeen(store)).toEqual({ world: '2026-11-21T12:00:00Z' });
	});

	it('ignores corrupt or invalid stored values', () => {
		expect(loadLastSeen(memoryStore({ 'skein.lastSeen.v1': 'not json' }))).toEqual({});
		expect(loadLastSeen(memoryStore({ 'skein.lastSeen.v1': '[1,2]' }))).toEqual({});
		const mixed = JSON.stringify({ a: '2026-11-21T12:00:00Z', b: 'yesterday', c: 5 });
		expect(loadLastSeen(memoryStore({ 'skein.lastSeen.v1': mixed }))).toEqual({
			a: '2026-11-21T12:00:00Z'
		});
	});

	it('survives a store that throws on write', () => {
		const store = {
			getItem: () => null,
			setItem: () => {
				throw new Error('QuotaExceeded');
			}
		};
		expect(() => markSeen('world', '2026-11-21T12:00:00Z', store)).not.toThrow();
	});

	it('compares instants, not strings (fractional seconds)', () => {
		// As strings, ".5Z" sorts before "Z"; as instants it is later.
		expect(isNew(item('2026-11-21T12:00:00.5Z'), '2026-11-21T12:00:00Z')).toBe(true);
		expect(isNew(item('2026-11-21T12:00:00Z'), '2026-11-21T12:00:00Z')).toBe(false);
	});

	it('counts everything as new before the first visit', () => {
		expect(isNew(item('2020-01-01T00:00:00Z'), undefined)).toBe(true);
	});

	it('newCount ignores collapsed items', () => {
		const items = [
			item('2026-11-21T13:00:00Z'),
			item('2026-11-21T14:00:00Z', true),
			item('2026-11-21T11:00:00Z')
		];
		expect(newCount(items, '2026-11-21T12:00:00Z')).toBe(1);
		expect(newCount(items, undefined)).toBe(2);
	});

	it('latestFirstSeen', () => {
		expect(latestFirstSeen([])).toBeUndefined();
		expect(
			latestFirstSeen([item('2026-11-21T12:00:00Z'), item('2026-11-21T12:00:00.25Z')])
		).toBe('2026-11-21T12:00:00.25Z');
	});
});
