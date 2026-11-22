import { describe, expect, it } from 'vitest';
import { groupByLocalDay } from './group';
import type { Day, ExportItem } from './types';

function item(id: string, published_at: string, importance: number, collapsed = false): ExportItem {
	return {
		id,
		title: id,
		url: `https://example.com/${id}`,
		source_id: 's',
		published_at,
		first_seen_at: published_at,
		excerpt: null,
		importance,
		also_covered_by: [],
		collapsed
	};
}

describe('groupByLocalDay', () => {
	const days: Day[] = [
		{
			date: '2026-11-22',
			items: [item('late-evening-ny', '2026-11-22T02:00:00Z', 0.5)]
		},
		{
			date: '2026-11-21',
			items: [
				item('a', '2026-11-21T15:00:00Z', 0.2),
				item('b', '2026-11-21T14:00:00Z', 0.9),
				item('c', '2026-11-21T13:00:00Z', 0.8, true),
				item('d', '2026-11-21T12:00:00Z', 0.95, true)
			]
		},
		{ date: '2026-11-20', items: [item('e', '2026-11-20T10:00:00Z', 0.4)] }
	];

	it('merges UTC days into local days, newest first', () => {
		const ny = groupByLocalDay(days, 'America/New_York');
		expect(ny.map((d) => d.key)).toEqual(['2026-11-21', '2026-11-20']);
		expect(ny[0].shown.map((i) => i.id)).toEqual(['b', 'late-evening-ny', 'a']);

		const utc = groupByLocalDay(days, 'UTC');
		expect(utc.map((d) => d.key)).toEqual(['2026-11-22', '2026-11-21', '2026-11-20']);
	});

	it('keeps collapsed items apart, ranked by importance', () => {
		const [today] = groupByLocalDay(days, 'UTC').slice(1);
		expect(today.shown.map((i) => i.id)).toEqual(['b', 'a']);
		expect(today.more.map((i) => i.id)).toEqual(['d', 'c']);
	});

	it('handles an empty feed', () => {
		expect(groupByLocalDay([])).toEqual([]);
	});
});
