import { env } from 'cloudflare:test';
import { beforeEach, describe, expect, it } from 'vitest';
import {
	apply,
	empty,
	KEY,
	MAX_SPLIT_ITEMS,
	MAX_TITLE,
	OP_TTL_DAYS,
	parse,
	type Action,
	type Overrides
} from '../src/overrides';
import { call, OWNER, PIPELINE, resetKv } from './helpers';

beforeEach(resetKv);

const NOW = Date.parse('2026-11-23T12:00:00Z');
const DAY = 24 * 3600 * 1000;
const rand = (bytes: number) => 'ab'.repeat(bytes);
const run = (doc: Overrides, ...actions: Action[]) =>
	actions.reduce((d, a, i) => apply(d, a, NOW + i, rand), doc);

describe('parse', () => {
	it.each([
		[{ action: 'rename', thread: 't1', title: '  Gemini   models ' }, { action: 'rename', thread: 't1', title: 'Gemini models' }],
		[{ action: 'rename', thread: 't1', title: null }, { action: 'rename', thread: 't1', title: null }],
		[{ action: 'pin', thread: 'markets--energy' }, { action: 'pin', thread: 'markets--energy' }],
		[{ action: 'merge', from: 't1', into: 't2' }, { action: 'merge', from: 't1', into: 't2' }],
		[{ action: 'split', thread: 't1', items: ['a', 'b', 'a'] }, { action: 'split', thread: 't1', items: ['a', 'b'] }],
		[{ action: 'move', item: 'i1', to: 't2' }, { action: 'move', item: 'i1', to: 't2' }]
	])('accepts %j', (body, expected) => {
		expect(parse(body)).toEqual({ ok: true, value: expected });
	});

	it.each([
		['not an object', []],
		['no action', { thread: 't1' }],
		['an unknown action', { action: 'delete', thread: 't1' }],
		['an unknown field', { action: 'pin', thread: 't1', title: 'x' }],
		['a missing id', { action: 'mute' }],
		['an invalid id', { action: 'mute', thread: 'has space' }],
		['an empty title', { action: 'rename', thread: 't1', title: '   ' }],
		['a long title', { action: 'rename', thread: 't1', title: 'x'.repeat(MAX_TITLE + 1) }],
		['a self-merge', { action: 'merge', from: 't1', into: 't1' }],
		['a split with no items', { action: 'split', thread: 't1', items: [] }],
		['a split with too many items', { action: 'split', thread: 't1', items: Array.from({ length: MAX_SPLIT_ITEMS + 1 }, (_, i) => `i${i}`) }],
		['a bad item id', { action: 'split', thread: 't1', items: ['ok', 3] }]
	])('rejects %s', (_, body) => {
		expect(parse(body).ok).toBe(false);
	});
});

describe('apply', () => {
	it('keeps settings per thread and drops entries that become empty', () => {
		const doc = run(
			empty(),
			{ action: 'rename', thread: 't1', title: 'Gemini' },
			{ action: 'pin', thread: 't1' },
			{ action: 'mute', thread: 't2' }
		);
		expect(doc.threads).toEqual({ t1: { title: 'Gemini', pinned: true }, t2: { muted: true } });
		const cleared = run(
			doc,
			{ action: 'rename', thread: 't1', title: null },
			{ action: 'unpin', thread: 't1' },
			{ action: 'unmute', thread: 't2' }
		);
		expect(cleared.threads).toEqual({});
		expect(cleared.updated_at).toBe(new Date(NOW + 2).toISOString());
	});

	it('records structural ops with ids, in order', () => {
		const doc = run(
			empty(),
			{ action: 'merge', from: 't1', into: 't2' },
			{ action: 'split', thread: 't2', items: ['a', 'b'] },
			{ action: 'move', item: 'c', to: 't3' }
		);
		expect(doc.ops).toEqual([
			{ id: `op-${NOW.toString(36)}-abababab`, at: new Date(NOW).toISOString(), type: 'merge', from: 't1', into: 't2' },
			{ id: `op-${(NOW + 1).toString(36)}-abababab`, at: new Date(NOW + 1).toISOString(), type: 'split', thread: 't2', items: ['a', 'b'], new_id: 'uabababababab' },
			{ id: `op-${(NOW + 2).toString(36)}-abababab`, at: new Date(NOW + 2).toISOString(), type: 'move', item: 'c', to: 't3' }
		]);
	});

	it("drops a merged-away thread's settings", () => {
		const doc = run(empty(), { action: 'pin', thread: 't1' }, { action: 'merge', from: 't1', into: 't2' });
		expect(doc.threads).toEqual({});
	});

	it(`prunes ops older than ${OP_TTL_DAYS} days on the next write`, () => {
		const old = apply(empty(), { action: 'move', item: 'a', to: 't1' }, NOW - (OP_TTL_DAYS + 1) * DAY, rand);
		const recent = apply(old, { action: 'move', item: 'b', to: 't1' }, NOW - DAY, rand);
		const next = apply(recent, { action: 'pin', thread: 't9' }, NOW, rand);
		expect(next.ops.map((o) => (o as { item: string }).item)).toEqual(['b']);
	});

	it('never mutates its input', () => {
		const doc = run(empty(), { action: 'pin', thread: 't1' });
		const before = JSON.stringify(doc);
		run(doc, { action: 'unpin', thread: 't1' }, { action: 'merge', from: 't1', into: 't2' });
		expect(JSON.stringify(doc)).toBe(before);
	});
});

describe('GET/POST /overrides', () => {
	it('starts empty', async () => {
		const res = await call('/overrides', { token: OWNER });
		expect(await res.json()).toEqual(empty());
	});

	it('POST applies one action and returns the document; GET reads it back', async () => {
		const res = await call('/overrides', {
			method: 'POST',
			token: OWNER,
			body: { action: 'split', thread: 't1', items: ['a', 'b'] }
		});
		expect(res.status).toBe(200);
		const doc = (await res.json()) as Overrides;
		expect(doc.ops).toHaveLength(1);
		expect(doc.ops[0]).toMatchObject({ type: 'split', thread: 't1', items: ['a', 'b'] });
		expect((doc.ops[0] as { new_id: string }).new_id).toMatch(/^u[0-9a-f]{12}$/);
		expect(await (await call('/overrides', { token: OWNER })).json()).toEqual(doc);
		expect(await env.SKEIN.get(KEY, 'json')).toEqual(doc);
	});

	it('the pipeline token can read but not write', async () => {
		await call('/overrides', { method: 'POST', token: OWNER, body: { action: 'mute', thread: 't1' } });
		const read = await call('/overrides', { token: PIPELINE });
		expect(read.status).toBe(200);
		expect(((await read.json()) as Overrides).threads).toEqual({ t1: { muted: true } });
		const write = await call('/overrides', {
			method: 'POST',
			token: PIPELINE,
			body: { action: 'unmute', thread: 't1' }
		});
		expect(write.status).toBe(403);
	});

	it('400 for invalid actions, 401 without a token', async () => {
		const bad = await call('/overrides', {
			method: 'POST',
			token: OWNER,
			body: { action: 'merge', from: 't1', into: 't1' }
		});
		expect(bad.status).toBe(400);
		expect((await call('/overrides')).status).toBe(401);
	});
});
