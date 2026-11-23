import { describe, expect, it } from 'vitest';
import {
	isNew,
	latestFirstSeen,
	loadLastSeen,
	loadThreadSeen,
	markSeen,
	markThreadSeen,
	newCount,
	newSince,
	seedThreadSeen,
	topicLatestFirstSeen,
	topicNewCount
} from './readState';
import type { ExportItem, ThreadSummary, TopicFeed } from './types';

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

describe('topics with threads', () => {
	function thread(first_seen: string[], latest_first_seen_at: string): ThreadSummary {
		return {
			id: 't',
			title: 't',
			kind: 'story',
			state: 'active',
			last_item_at: latest_first_seen_at,
			item_count: first_seen.length,
			collapsed_count: 0,
			latest_first_seen_at,
			first_seen,
			latest: item(latest_first_seen_at)
		};
	}
	const feed: TopicFeed = {
		schema_version: 2,
		id: 'world',
		name: 'World',
		group: 'news',
		mode: 'threaded',
		threads: [
			thread(['2026-11-21T12:00:00Z', '2026-11-21T08:00:00Z'], '2026-11-21T13:00:00Z'),
			thread(['2026-11-20T12:00:00Z'], '2026-11-20T12:00:00Z')
		],
		days: [
			{
				date: '2026-11-21',
				items: [item('2026-11-21T11:00:00Z'), item('2026-11-21T11:30:00Z', true)]
			}
		]
	};

	it('counts new single items and new thread items', () => {
		expect(topicNewCount(feed, '2026-11-21T10:00:00Z')).toBe(2); // one single, one thread item
		expect(topicNewCount(feed, undefined)).toBe(4); // collapsed singles never count
		expect(topicNewCount(feed, '2026-11-22T00:00:00Z')).toBe(0);
	});

	it('newSince counts instants after the last visit', () => {
		expect(newSince(['2026-11-21T12:00:00Z', '2026-11-21T08:00:00Z'], '2026-11-21T10:00:00Z')).toBe(1);
		expect(newSince(['2026-11-21T12:00:00Z'], undefined)).toBe(1);
	});

	it('the latest first-seen includes thread items', () => {
		expect(topicLatestFirstSeen(feed)).toBe('2026-11-21T13:00:00Z');
		expect(topicLatestFirstSeen({ ...feed, threads: [] })).toBe('2026-11-21T11:30:00Z');
	});
});

describe('thread read state', () => {
	it('is stored apart from topics and never moves backwards', () => {
		const store = memoryStore();
		markSeen('world', '2026-11-21T12:00:00Z', store);
		markThreadSeen('t1', '2026-11-21T10:00:00Z', store);
		markThreadSeen('t1', '2026-11-21T09:00:00Z', store);
		expect(loadThreadSeen(store)).toEqual({ t1: '2026-11-21T10:00:00Z' });
		expect(loadLastSeen(store)).toEqual({ world: '2026-11-21T12:00:00Z' });
		expect([...store.data.keys()].sort()).toEqual(['skein.lastSeen.v1', 'skein.threadSeen.v1']);
	});

	it('seeds unopened threads with the topic previous visit only', () => {
		const store = memoryStore();
		markThreadSeen('opened', '2026-11-21T11:00:00Z', store);
		seedThreadSeen(['opened', 'fresh'], '2026-11-20T08:00:00Z', store);
		expect(loadThreadSeen(store)).toEqual({
			opened: '2026-11-21T11:00:00Z', // its own visit wins, even if older seeds come later
			fresh: '2026-11-20T08:00:00Z'
		});
	});

	it('does not seed on a first topic visit', () => {
		const store = memoryStore();
		seedThreadSeen(['t1'], undefined, store);
		expect(loadThreadSeen(store)).toEqual({});
		expect(store.data.size).toBe(0);
	});

	it('a seeded thread moves forward when opened', () => {
		const store = memoryStore();
		seedThreadSeen(['t1'], '2026-11-20T08:00:00Z', store);
		markThreadSeen('t1', '2026-11-21T12:00:00Z', store);
		expect(loadThreadSeen(store).t1).toBe('2026-11-21T12:00:00Z');
	});
});
