import { describe, expect, it } from 'vitest';
import { buildSpine, pickThread } from './spine';
import { item, threadFeed, threadSummary, topic } from './testFixtures';

const at = (h: number) => `2026-11-21T${String(h).padStart(2, '0')}:00:00Z`;

describe('spine mock', () => {
	it('puts items in time order and hangs every third off the node before it', () => {
		const items = [5, 1, 3, 2, 4, 6, 7].map((h) => item(`i${h}`, at(h)));
		const spine = buildSpine(threadFeed('t', 'world', items), null);
		expect(spine.nodes.map((n) => n.item.id)).toEqual(['i1', 'i2', 'i4', 'i5', 'i7']);
		expect(spine.nodes[1].branches.map((b) => b.id)).toEqual(['i3']);
		expect(spine.nodes[3].branches.map((b) => b.id)).toEqual(['i6']);
		expect(spine.branchCount).toBe(2);
	});

	it('lists the topic’s other threads as related, newest first, capped', () => {
		const t = topic(
			'world',
			'threaded',
			['t', 'a', 'b', 'c'].map((id, i) => threadSummary(id, at(i + 1))),
			[]
		);
		const spine = buildSpine(threadFeed('t', 'world', [item('x', at(1))]), t, 2);
		expect(spine.related.map((r) => r.id)).toEqual(['c', 'b']);
	});

	it('picks the requested thread, else the biggest in the topic, else anywhere', () => {
		const world = topic(
			'world',
			'threaded',
			[threadSummary('small', at(1)), threadSummary('big', at(2), { item_count: 9 })],
			[]
		);
		const tech = topic('tech', 'tracker', [threadSummary('huge', at(3), { item_count: 20 })], []);
		const flat = topic('gadgets', 'flat', [], []);
		expect(pickThread([world, tech], 'world', 'small')).toEqual({ topicId: 'world', threadId: 'small' });
		expect(pickThread([world, tech], 'world', null)).toEqual({ topicId: 'world', threadId: 'big' });
		expect(pickThread([world, tech, flat], 'gadgets', null)).toEqual({ topicId: 'tech', threadId: 'huge' });
		expect(pickThread([flat], null, null)).toBeNull();
	});
});
