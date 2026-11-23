import { env } from 'cloudflare:test';
import { beforeEach, describe, expect, it } from 'vitest';
import { KEY, MAX_ENTRIES, merge, parse, PRUNE_AFTER_DAYS, type ReadState } from '../src/readState';
import { call, OWNER, PIPELINE, resetKv } from './helpers';

beforeEach(resetKv);

const DAY = 24 * 3600 * 1000;
const NOW = Date.parse('2026-11-23T12:00:00Z');
const state = (topics = {}, threads = {}): ReadState => ({ topics, threads });

describe('parse', () => {
	it('accepts either section and normalizes instants', () => {
		const r = parse({ topics: { world: '2026-11-23T10:00:00+02:00' } }, NOW);
		expect(r).toEqual({ ok: true, value: state({ world: '2026-11-23T08:00:00.000Z' }) });
	});

	it.each([
		['an array', []],
		['null', null],
		['an unknown field', { topics: {}, extra: 1 }],
		['a section that is not an object', { threads: ['t1'] }],
		['an invalid id', { topics: { 'has space': '2026-11-23T10:00:00Z' } }],
		['a non-instant value', { topics: { world: 'yesterday' } }],
		['a number value', { topics: { world: 5 } }],
		['an instant far in the future', { topics: { world: '2027-01-01T00:00:00Z' } }]
	])('rejects %s', (_, body) => {
		expect(parse(body, NOW).ok).toBe(false);
	});

	it('caps entries per section', () => {
		const many = Object.fromEntries(
			Array.from({ length: MAX_ENTRIES + 1 }, (_, i) => [`t${i}`, '2026-11-23T10:00:00Z'])
		);
		expect(parse({ threads: many }, NOW).ok).toBe(false);
	});
});

describe('merge', () => {
	const stored = state(
		{ world: '2026-11-23T10:00:00.000Z' },
		{ t1: '2026-11-22T10:00:00.000Z', t2: '2026-11-23T09:00:00.000Z' }
	);

	it('keeps the later instant per id, never moving backwards', () => {
		const incoming = state(
			{ world: '2026-11-23T08:00:00.000Z', politics: '2026-11-23T07:00:00.000Z' },
			{ t1: '2026-11-23T11:00:00.000Z' }
		);
		const { state: out, changed } = merge(stored, incoming, NOW);
		expect(changed).toBe(true);
		expect(out).toEqual(
			state(
				{ politics: '2026-11-23T07:00:00.000Z', world: '2026-11-23T10:00:00.000Z' },
				{ t1: '2026-11-23T11:00:00.000Z', t2: '2026-11-23T09:00:00.000Z' }
			)
		);
	});

	it('reports no change when nothing is newer', () => {
		const older = state({ world: '2026-11-20T00:00:00.000Z' }, {});
		expect(merge(stored, older, NOW)).toEqual({ state: stored, changed: false });
		expect(merge(stored, state(), NOW).changed).toBe(false);
	});

	it(`prunes entries older than ${PRUNE_AFTER_DAYS} days`, () => {
		const old = new Date(NOW - (PRUNE_AFTER_DAYS + 1) * DAY).toISOString();
		const { state: out, changed } = merge(state({ gone: old }), state({ fresh: old }), NOW);
		expect(out).toEqual(state());
		expect(changed).toBe(true); // the stored entry was dropped
		expect(merge(state(), state({ fresh: old }), NOW).changed).toBe(false);
	});
});

describe('GET/PUT /read-state', () => {
	it('starts empty', async () => {
		const res = await call('/read-state', { token: OWNER });
		expect(res.status).toBe(200);
		expect(await res.json()).toEqual(state());
	});

	it('PUT merges and returns the merged document; GET reads it back', async () => {
		const recent = new Date(Date.now() - DAY).toISOString();
		const newer = new Date(Date.now() - 3600_000).toISOString();
		await call('/read-state', { method: 'PUT', token: OWNER, body: { topics: { world: newer } } });
		const res = await call('/read-state', {
			method: 'PUT',
			token: OWNER,
			body: { topics: { world: recent }, threads: { t1: recent } } // another device, behind
		});
		expect(res.status).toBe(200);
		const merged = { topics: { world: newer }, threads: { t1: recent } };
		expect(await res.json()).toEqual(merged);
		expect(await (await call('/read-state', { token: OWNER })).json()).toEqual(merged);
		expect(await env.SKEIN.get(KEY, 'json')).toEqual(merged);
	});

	it('400 for an invalid body, 413 for a huge one', async () => {
		const bad = await call('/read-state', { method: 'PUT', token: OWNER, body: { topics: 3 } });
		expect(bad.status).toBe(400);
		expect((await bad.json()) as object).toMatchObject({ error: { code: 'bad_request' } });
		const notJson = await call('/read-state', { method: 'PUT', token: OWNER, body: '{nope' });
		expect(notJson.status).toBe(400);
		const huge = await call('/read-state', {
			method: 'PUT',
			token: OWNER,
			body: { topics: { world: 'x'.repeat(300 * 1024) } }
		});
		expect(huge.status).toBe(413);
	});

	it('is owner-only', async () => {
		expect((await call('/read-state')).status).toBe(401);
		expect((await call('/read-state', { token: PIPELINE })).status).toBe(403);
		expect((await call('/read-state', { method: 'PUT', token: PIPELINE, body: {} })).status).toBe(403);
	});
});
