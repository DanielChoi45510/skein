import { describe, expect, it } from 'vitest';
import {
	callWorker,
	cleanToken,
	forgetToken,
	loadToken,
	ownerFeaturesAvailable,
	saveToken,
	verifyToken,
	waitLabel,
	WorkerError
} from './owner';

const BASE = 'https://owner.example.workers.dev';

function memoryStore() {
	const data = new Map<string, string>();
	return { data, getItem: (k: string) => data.get(k) ?? null, setItem: (k: string, v: string) => void data.set(k, v) };
}

function fakeFetch(status: number, body: unknown = null, headers: Record<string, string> = {}) {
	const calls: { url: string; init: RequestInit }[] = [];
	const impl = (async (url: string, init: RequestInit) => {
		calls.push({ url, init });
		return new Response(body === null ? null : JSON.stringify(body), { status, headers });
	}) as unknown as typeof fetch;
	return { impl, calls };
}

describe('token storage', () => {
	it('saves, loads and forgets', () => {
		const store = memoryStore();
		expect(loadToken(store)).toBeNull();
		saveToken('abc123', store);
		expect(loadToken(store)).toBe('abc123');
		forgetToken(store);
		expect(loadToken(store)).toBeNull();
	});

	it('survives blocked storage', () => {
		const broken = {
			getItem: () => {
				throw new Error('blocked');
			},
			setItem: () => {
				throw new Error('blocked');
			}
		};
		expect(loadToken(broken)).toBeNull();
		expect(() => saveToken('x', broken)).not.toThrow();
		expect(() => forgetToken(broken)).not.toThrow();
	});

	it('cleans pasted tokens', () => {
		expect(cleanToken('  abc \n')).toBe('abc');
		expect(cleanToken('Bearer abc')).toBe('abc');
	});

	it('owner features need a Worker URL in the build', () => {
		expect(ownerFeaturesAvailable('')).toBe(false);
		expect(ownerFeaturesAvailable(BASE)).toBe(true);
		expect(ownerFeaturesAvailable()).toBe(false); // tests build without PUBLIC_WORKER_URL
	});
});

describe('callWorker', () => {
	it('sends the bearer token to the Worker, never caching', async () => {
		const f = fakeFetch(200, { ok: true });
		await callWorker('/read-state', 'tok', { method: 'PUT', body: '{}' }, { base: BASE, fetchImpl: f.impl });
		const [c] = f.calls;
		expect(c!.url).toBe(`${BASE}/read-state`);
		const headers = new Headers(c!.init.headers);
		expect(headers.get('authorization')).toBe('Bearer tok');
		expect(headers.get('content-type')).toBe('application/json');
		expect(c!.init.cache).toBe('no-store');
	});

	it.each([
		[401, 'unauthorized'],
		[403, 'forbidden'],
		[502, 'failed']
	])('HTTP %i → %s', async (status, kind) => {
		const f = fakeFetch(status, { error: { code: 'x', message: 'Worker said no.' } });
		await expect(callWorker('/auth', 't', {}, { base: BASE, fetchImpl: f.impl })).rejects.toMatchObject({ kind });
	});

	it('passes on the Worker message and retry-after for 429', async () => {
		const f = fakeFetch(429, { error: { code: 'rate_limited', message: 'Refreshed recently. Try again in 120 s.' } }, { 'retry-after': '120' });
		const err = await callWorker('/refresh', 't', { method: 'POST' }, { base: BASE, fetchImpl: f.impl }).catch((e) => e);
		expect(err).toBeInstanceOf(WorkerError);
		expect(err).toMatchObject({ kind: 'rate_limited', retryAfter: 120, message: 'Refreshed recently. Try again in 120 s.' });
	});

	it('network failure → unreachable', async () => {
		const impl = (async () => {
			throw new TypeError('Failed to fetch');
		}) as unknown as typeof fetch;
		await expect(callWorker('/auth', 't', {}, { base: BASE, fetchImpl: impl })).rejects.toMatchObject({ kind: 'unreachable' });
	});

	it('refuses to call without a Worker URL', async () => {
		await expect(callWorker('/auth', 't', {}, { base: '' })).rejects.toMatchObject({ kind: 'failed' });
	});
});

describe('verifyToken', () => {
	it.each([
		[204, 'ok'],
		[401, 'invalid'],
		[403, 'invalid'], // e.g. the pipeline token pasted by mistake
		[429, 'rate_limited'],
		[500, 'failed']
	])('HTTP %i → %s', async (status, expected) => {
		expect(await verifyToken('t', { base: BASE, fetchImpl: fakeFetch(status).impl })).toBe(expected);
	});
});

describe('waitLabel', () => {
	it('counts down minutes, then seconds, then nothing', () => {
		expect(waitLabel(300_000, 0)).toBe('Wait 5 min');
		expect(waitLabel(61_000, 0)).toBe('Wait 2 min');
		expect(waitLabel(40_000, 0)).toBe('Wait 40 s');
		expect(waitLabel(0, 0)).toBeNull();
	});
});
