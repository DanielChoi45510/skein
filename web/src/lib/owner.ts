// Owner access (DESIGN §9.2, §10.2): the owner pastes their token once per device
// on /settings/; it's kept in this browser's localStorage and sent as a bearer token
// to the owner Worker. Visitors never see owner controls, and without a Worker URL
// in the build there are no owner features at all.
//
// The token is never displayed, logged or put in a URL. If the Worker rejects it
// (401), it's forgotten here, so a rotated token can't leave a stale one behind.

import { safeStorage, type Store } from './readState';

export const WORKER_URL: string = __WORKER_URL__;
export const ownerFeaturesAvailable = (base: string = WORKER_URL) => base !== '';

const TOKEN_KEY = 'skein.owner.v1';

export function loadToken(store: Store = safeStorage()): string | null {
	try {
		const token = store.getItem(TOKEN_KEY);
		return token ? token : null;
	} catch {
		return null;
	}
}

export function saveToken(token: string, store: Store = safeStorage()): void {
	try {
		store.setItem(TOKEN_KEY, token);
	} catch {
		// storage blocked: the token works for this page only
	}
}

export function forgetToken(store: Store = safeStorage()): void {
	try {
		store.setItem(TOKEN_KEY, '');
	} catch {
		// nothing stored
	}
}

/** Tidy a pasted token: no surrounding whitespace, no "Bearer " prefix. */
export function cleanToken(raw: string): string {
	return raw.trim().replace(/^Bearer\s+/i, '');
}

export type WorkerErrorKind = 'unauthorized' | 'forbidden' | 'rate_limited' | 'unreachable' | 'failed';

export class WorkerError extends Error {
	constructor(
		readonly kind: WorkerErrorKind,
		message: string,
		readonly retryAfter?: number // seconds, for rate_limited
	) {
		super(message);
	}
}

type Fetch = typeof fetch;

/** Call the Worker with the token; resolves for 2xx, throws WorkerError otherwise. */
export async function callWorker(
	path: string,
	token: string,
	init: RequestInit = {},
	{ base = WORKER_URL, fetchImpl = fetch }: { base?: string; fetchImpl?: Fetch } = {}
): Promise<Response> {
	if (!base) throw new WorkerError('failed', 'Owner features are not set up on this site.');
	const headers = new Headers(init.headers);
	headers.set('authorization', `Bearer ${token}`);
	if (init.body !== undefined) headers.set('content-type', 'application/json');
	let res: Response;
	try {
		res = await fetchImpl(`${base}${path}`, { ...init, headers, cache: 'no-store' });
	} catch {
		throw new WorkerError('unreachable', "Couldn't reach the owner service. Check your connection.");
	}
	if (res.ok) return res;
	const message = await res
		.json()
		.then((d: { error?: { message?: string } }) => d.error?.message)
		.catch(() => undefined);
	if (res.status === 401) throw new WorkerError('unauthorized', 'The owner token was rejected.');
	if (res.status === 403) throw new WorkerError('forbidden', 'This token cannot do that.');
	if (res.status === 429) {
		const retry = Number(res.headers.get('retry-after'));
		throw new WorkerError(
			'rate_limited',
			message ?? 'Too many requests; try again shortly.',
			Number.isFinite(retry) && retry > 0 ? retry : undefined
		);
	}
	throw new WorkerError('failed', message ?? `The owner service failed (HTTP ${res.status}).`);
}

export type VerifyResult = 'ok' | 'invalid' | 'rate_limited' | 'unreachable' | 'failed';

/** Check a token against GET /auth without changing anything. */
export async function verifyToken(
	token: string,
	opts: { base?: string; fetchImpl?: Fetch } = {}
): Promise<VerifyResult> {
	try {
		await callWorker('/auth', token, {}, opts);
		return 'ok';
	} catch (e) {
		if (!(e instanceof WorkerError)) return 'failed';
		if (e.kind === 'unauthorized' || e.kind === 'forbidden') return 'invalid';
		return e.kind === 'rate_limited' || e.kind === 'unreachable' ? e.kind : 'failed';
	}
}

/** Label for the refresh button while it's cooling down ("Wait 4 min", "Wait 40 s"). */
export function waitLabel(untilMs: number, nowMs: number): string | null {
	const left = Math.ceil((untilMs - nowMs) / 1000);
	if (left <= 0) return null;
	return left >= 60 ? `Wait ${Math.ceil(left / 60)} min` : `Wait ${left} s`;
}
