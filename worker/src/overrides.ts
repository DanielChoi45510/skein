// GET/POST /overrides (DESIGN §5 "Owner overrides", §10.2): the owner's corrections
// to threads, read by the pipeline at the start of each run.
//
// One JSON document in KV (key `overrides`):
//   threads  thread id → {title?, pinned?, muted?}   settings, applied on every run
//   ops      [{id, at, type, ...}]                    structural one-shot operations:
//            merge (from → into), split (items of a thread → new thread),
//            move (one item → another thread)
// The pipeline applies each op once, in `at` order, and records the ids it applied
// (on the data branch), so reruns never apply one twice. Ops older than OP_TTL_DAYS
// are pruned here: by then every hourly run has seen them.
//
// The Worker doesn't know which threads or items exist; the pipeline skips (and
// logs) ops that point at things that are gone. Writes are rare (owner actions), so
// the read-modify-write in KV is fine; two actions at the same instant could race
// (last write wins), which a single owner won't hit in practice.

import type { Context } from './index';
import { error, json, readJson } from './http';

export const KEY = 'overrides';
export const MAX_BODY_BYTES = 16 * 1024;
export const MAX_TITLE = 120;
export const MAX_SPLIT_ITEMS = 50;
export const MAX_OPS = 500;
export const MAX_THREAD_SETTINGS = 2000;
export const OP_TTL_DAYS = 30;
const ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$/;

export interface ThreadSettings {
	title?: string;
	pinned?: true;
	muted?: true;
}

interface OpBase {
	id: string;
	at: string; // ISO instant the owner made the change
}
export type Op =
	| (OpBase & { type: 'merge'; from: string; into: string })
	| (OpBase & { type: 'split'; thread: string; items: string[]; new_id: string })
	| (OpBase & { type: 'move'; item: string; to: string });

/** Omit applied to each member of a union (plain Omit would collapse it). */
type DistributiveOmit<T, K extends PropertyKey> = T extends unknown ? Omit<T, K> : never;

export interface Overrides {
	version: 1;
	updated_at: string | null;
	threads: Record<string, ThreadSettings>;
	ops: Op[];
}

export type Action =
	| { action: 'rename'; thread: string; title: string | null } // null: back to automatic
	| { action: 'pin' | 'unpin' | 'mute' | 'unmute'; thread: string }
	| { action: 'merge'; from: string; into: string }
	| { action: 'split'; thread: string; items: string[] }
	| { action: 'move'; item: string; to: string };

export const empty = (): Overrides => ({ version: 1, updated_at: null, threads: {}, ops: [] });

type Parsed = { ok: true; value: Action } | { ok: false; message: string };

function id(v: unknown, field: string): string | { message: string } {
	return typeof v === 'string' && ID.test(v) ? v : { message: `\`${field}\` must be an id.` };
}

/** Validate a POST body: exactly one action, no unknown fields. */
export function parse(body: unknown): Parsed {
	if (!body || typeof body !== 'object' || Array.isArray(body)) {
		return { ok: false, message: 'Expected an object with an `action`.' };
	}
	const b = body as Record<string, unknown>;
	const allowed: Record<string, string[]> = {
		rename: ['thread', 'title'],
		pin: ['thread'],
		unpin: ['thread'],
		mute: ['thread'],
		unmute: ['thread'],
		merge: ['from', 'into'],
		split: ['thread', 'items'],
		move: ['item', 'to']
	};
	const action = typeof b.action === 'string' ? b.action : '';
	const fields = allowed[action];
	if (!fields) return { ok: false, message: `Unknown action: ${String(b.action)}.` };
	const extra = Object.keys(b).filter((k) => k !== 'action' && !fields.includes(k));
	if (extra.length) return { ok: false, message: `Unknown field for ${action}: ${extra[0]}.` };

	const ids: Record<string, string> = {};
	for (const f of fields.filter((f) => f !== 'title' && f !== 'items')) {
		const r = id(b[f], f);
		if (typeof r !== 'string') return { ok: false, message: r.message };
		ids[f] = r;
	}
	switch (action) {
		case 'rename': {
			if (b.title === null) return { ok: true, value: { action, thread: ids.thread!, title: null } };
			const title = typeof b.title === 'string' ? b.title.replace(/\s+/g, ' ').trim() : '';
			if (!title || title.length > MAX_TITLE) {
				return { ok: false, message: `\`title\` must be 1-${MAX_TITLE} characters, or null.` };
			}
			return { ok: true, value: { action, thread: ids.thread!, title } };
		}
		case 'merge':
			if (ids.from === ids.into) return { ok: false, message: 'Cannot merge a thread into itself.' };
			return { ok: true, value: { action, from: ids.from!, into: ids.into! } };
		case 'split': {
			if (!Array.isArray(b.items) || !b.items.length || b.items.length > MAX_SPLIT_ITEMS) {
				return { ok: false, message: `\`items\` must list 1-${MAX_SPLIT_ITEMS} item ids.` };
			}
			const items: string[] = [];
			for (const item of b.items) {
				const r = id(item, 'items');
				if (typeof r !== 'string') return { ok: false, message: r.message };
				if (!items.includes(r)) items.push(r);
			}
			return { ok: true, value: { action, thread: ids.thread!, items } };
		}
		case 'move':
			return { ok: true, value: { action, item: ids.item!, to: ids.to! } };
		default:
			return {
				ok: true,
				value: { action: action as 'pin' | 'unpin' | 'mute' | 'unmute', thread: ids.thread! }
			};
	}
}

function randomHex(bytes: number): string {
	return [...crypto.getRandomValues(new Uint8Array(bytes))]
		.map((b) => b.toString(16).padStart(2, '0'))
		.join('');
}

/** Apply one action to the document (a copy); `now` and `rand` are injectable for tests. */
export function apply(
	doc: Overrides,
	a: Action,
	now: number,
	rand: (bytes: number) => string = randomHex
): Overrides {
	const at = new Date(now).toISOString();
	const threads = { ...doc.threads };
	const cutoff = now - OP_TTL_DAYS * 24 * 3600 * 1000;
	let ops = doc.ops.filter((op) => Date.parse(op.at) >= cutoff);

	const settings = (thread: string, update: (s: ThreadSettings) => void) => {
		const s = { ...threads[thread] };
		update(s);
		if (s.title === undefined && !s.pinned && !s.muted) delete threads[thread];
		else threads[thread] = s;
	};
	const op = (fields: DistributiveOmit<Op, 'id' | 'at'>): Op =>
		({ id: `op-${now.toString(36)}-${rand(4)}`, at, ...fields }) as Op;

	switch (a.action) {
		case 'rename':
			settings(a.thread, (s) => {
				if (a.title === null) delete s.title;
				else s.title = a.title;
			});
			break;
		case 'pin':
			settings(a.thread, (s) => (s.pinned = true));
			break;
		case 'unpin':
			settings(a.thread, (s) => delete s.pinned);
			break;
		case 'mute':
			settings(a.thread, (s) => (s.muted = true));
			break;
		case 'unmute':
			settings(a.thread, (s) => delete s.muted);
			break;
		case 'merge':
			delete threads[a.from]; // the merged-away thread's settings no longer apply
			ops = [...ops, op({ type: 'merge', from: a.from, into: a.into })];
			break;
		case 'split':
			// u-prefixed: never collides with the pipeline's t… and topic--… ids.
			ops = [...ops, op({ type: 'split', thread: a.thread, items: a.items, new_id: `u${rand(6)}` })];
			break;
		case 'move':
			ops = [...ops, op({ type: 'move', item: a.item, to: a.to })];
			break;
	}
	return { version: 1, updated_at: at, threads, ops };
}

export async function load(kv: KVNamespace): Promise<Overrides> {
	const stored = await kv.get<Overrides>(KEY, 'json');
	return stored ? { ...empty(), ...stored } : empty();
}

export async function getOverrides({ env }: Context): Promise<Response> {
	return json(await load(env.SKEIN));
}

export async function postOverrides({ request, env }: Context): Promise<Response> {
	const body = await readJson(request, MAX_BODY_BYTES);
	if (!body.ok) return body.response;
	const parsed = parse(body.value);
	if (!parsed.ok) return error(400, 'bad_request', parsed.message);
	const next = apply(await load(env.SKEIN), parsed.value, Date.now());
	if (next.ops.length > MAX_OPS || Object.keys(next.threads).length > MAX_THREAD_SETTINGS) {
		return error(400, 'bad_request', 'Too many overrides; wait for old operations to expire.');
	}
	await env.SKEIN.put(KEY, JSON.stringify(next));
	return json(next);
}
