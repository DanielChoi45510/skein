// GET/PUT /read-state (DESIGN §9.2, §10.2): the owner's "last seen" instants per
// topic and per thread, synced across devices.
//
// PUT merges instead of replacing: for every id the later instant wins, so a
// device that was offline (or is behind) can never move read state backwards, and
// two devices never conflict. The response is the merged document, so a client
// syncs in one round trip. Entries older than PRUNE_AFTER_DAYS are dropped (their
// topics and threads have long left the feed). KV is only written when something
// changed: the free tier allows 1,000 writes a day.
//
// Two simultaneous PUTs from different devices can race (KV is last-write-wins);
// the loser's newer entries come back with its next PUT, because clients always
// send their whole local state.

import type { Context } from './index';
import { error, json, readJson } from './http';

export const KEY = 'read-state';
export const MAX_BODY_BYTES = 256 * 1024;
export const MAX_ENTRIES = 5000; // per section
export const PRUNE_AFTER_DAYS = 90;
const FUTURE_TOLERANCE_MS = 24 * 3600 * 1000;
const ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$/;
const SECTIONS = ['topics', 'threads'] as const;

type Section = (typeof SECTIONS)[number];
export type Seen = Record<string, string>; // id → ISO instant
export type ReadState = Record<Section, Seen>;

export const empty = (): ReadState => ({ topics: {}, threads: {} });

/** Validate a PUT body. Both sections are optional; nothing else is allowed. */
export function parse(
	body: unknown,
	now: number
): { ok: true; value: ReadState } | { ok: false; message: string } {
	if (!body || typeof body !== 'object' || Array.isArray(body)) {
		return { ok: false, message: 'Expected an object with `topics` and/or `threads`.' };
	}
	const extra = Object.keys(body).filter((k) => !(SECTIONS as readonly string[]).includes(k));
	if (extra.length) return { ok: false, message: `Unknown field: ${extra[0]}.` };
	const out = empty();
	for (const section of SECTIONS) {
		const raw = (body as Record<string, unknown>)[section];
		if (raw === undefined) continue;
		if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
			return { ok: false, message: `\`${section}\` must be an object of id → instant.` };
		}
		const entries = Object.entries(raw);
		if (entries.length > MAX_ENTRIES) {
			return { ok: false, message: `\`${section}\` has more than ${MAX_ENTRIES} entries.` };
		}
		for (const [id, instant] of entries) {
			if (!ID.test(id)) return { ok: false, message: `Invalid id in \`${section}\`.` };
			const t = typeof instant === 'string' ? Date.parse(instant) : NaN;
			if (Number.isNaN(t)) {
				return { ok: false, message: `\`${section}.${id}\` is not an ISO instant.` };
			}
			if (t > now + FUTURE_TOLERANCE_MS) {
				return { ok: false, message: `\`${section}.${id}\` is in the future.` };
			}
			out[section][id] = new Date(t).toISOString();
		}
	}
	return { ok: true, value: out };
}

/** Merge `incoming` into `stored` (later instant wins) and prune; reports whether anything changed. */
export function merge(
	stored: ReadState,
	incoming: ReadState,
	now: number
): { state: ReadState; changed: boolean } {
	const oldest = now - PRUNE_AFTER_DAYS * 24 * 3600 * 1000;
	const state = empty();
	let changed = false;
	for (const section of SECTIONS) {
		const ids = new Set([...Object.keys(stored[section]), ...Object.keys(incoming[section])]);
		for (const id of [...ids].sort()) {
			const a = stored[section][id];
			const b = incoming[section][id];
			const winner = a === undefined ? b! : b === undefined ? a : Date.parse(b) > Date.parse(a) ? b : a;
			if (Date.parse(winner) < oldest) {
				if (a !== undefined) changed = true; // pruned a stored entry
				continue;
			}
			if (winner !== a) changed = true;
			state[section][id] = winner;
		}
	}
	return { state, changed };
}

export async function load(kv: KVNamespace): Promise<ReadState> {
	const stored = await kv.get<Partial<ReadState>>(KEY, 'json');
	return { topics: stored?.topics ?? {}, threads: stored?.threads ?? {} };
}

export async function getReadState({ env }: Context): Promise<Response> {
	return json(await load(env.SKEIN));
}

export async function putReadState({ request, env }: Context): Promise<Response> {
	const body = await readJson(request, MAX_BODY_BYTES);
	if (!body.ok) return body.response;
	const now = Date.now();
	const parsed = parse(body.value, now);
	if (!parsed.ok) return error(400, 'bad_request', parsed.message);
	const { state, changed } = merge(await load(env.SKEIN), parsed.value, now);
	if (changed) await env.SKEIN.put(KEY, JSON.stringify(state));
	return json(state);
}
