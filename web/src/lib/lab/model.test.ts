import { describe, expect, it } from 'vitest';
import { age, buildTiles, leadEntry, perDay, shownCount, splitLead, tilesByGroup } from './model';
import { index, item, threadSummary, topic } from './testFixtures';

describe('lab model', () => {
	const world = topic(
		'world',
		'threaded',
		[threadSummary('t1', '2026-11-21T10:00:00Z', { item_count: 5, collapsed_count: 1 })],
		[item('a', '2026-11-21T11:00:00Z'), item('b', '2026-11-20T09:00:00Z', { collapsed: true })]
	);
	const gadgets = topic('gadgets', 'flat', [], [
		item('low', '2026-11-21T08:00:00Z', { importance: 0.2 }),
		item('high', '2026-11-20T08:00:00Z', { importance: 0.9 })
	]);

	it('counts shown items, thread items included, collapsed left out', () => {
		expect(shownCount(world)).toBe(1 + 4);
	});

	it('leads with the newest live thread, or a flat topic’s most important item', () => {
		expect(leadEntry(world)?.id).toBe('t1');
		const singles = topic('w', 'threaded', [], [item('x', '2026-11-21T08:00:00Z')]);
		expect(leadEntry(singles)?.id).toBe('x');
		const { lead, rest } = splitLead([
			{ kind: 'item', id: 'i', at: '2026-11-21T11:00:00Z', item: item('i', '2026-11-21T11:00:00Z') },
			{ kind: 'thread', id: 't', at: '2026-11-21T10:00:00Z', thread: threadSummary('t', '2026-11-21T10:00:00Z') }
		]);
		expect(lead?.id).toBe('t');
		expect(rest.map((e) => e.id)).toEqual(['i']);
		expect(leadEntry(gadgets)?.id).toBe('high');
		expect(leadEntry(topic('empty', 'flat', [], []))).toBeNull();
	});

	it('buckets first-seen instants into days ending at the export', () => {
		expect(perDay(world, '2026-11-21T12:00:00Z', 3)).toEqual([0, 1, 3]);
	});

	it('weights the busiest topic as the lead and idle topics as zero', () => {
		const idx = index([{ id: 'world' }, { id: 'gadgets' }, { id: 'leaks', has_sources: false }]);
		const tiles = buildTiles(idx, { world, gadgets, leaks: null }, {});
		const w = Object.fromEntries(tiles.map((t) => [t.id, t.weight]));
		expect(w).toEqual({ world: 3, gadgets: 2, leaks: 0 });
		expect(tiles.find((t) => t.id === 'world')?.newCount).toBe(1 + 2);
		expect(tilesByGroup(tiles)[0].tiles.at(-1)?.id).toBe('leaks');
	});
});

describe('lab formatting', () => {
	it('prints compact ages', () => {
		const now = Date.parse('2026-11-21T12:00:00Z');
		expect(age('2026-11-21T12:00:00Z', now)).toBe('now');
		expect(age('2026-11-21T11:48:00Z', now)).toBe('12m');
		expect(age('2026-11-21T07:00:00Z', now)).toBe('5h');
		expect(age('2026-11-18T12:00:00Z', now)).toBe('3d');
	});
});
