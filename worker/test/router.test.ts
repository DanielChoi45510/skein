import { describe, expect, it } from 'vitest';
import { call, freshIp, ORIGIN, OWNER, PIPELINE } from './helpers';

describe('auth', () => {
	it('accepts the owner token', async () => {
		const res = await call('/auth', { token: OWNER });
		expect(res.status).toBe(204);
		expect(res.headers.get('cache-control')).toBe('no-store');
	});

	it.each([
		['no token', undefined],
		['a wrong token', 'not-the-token'],
		['a prefix of the token', OWNER.slice(0, -1)]
	])('rejects %s with 401', async (_, token) => {
		const res = await call('/auth', { token });
		expect(res.status).toBe(401);
		expect(res.headers.get('www-authenticate')).toBe('Bearer');
		expect(await res.json()).toEqual({
			error: { code: 'unauthorized', message: 'Missing or invalid token.' }
		});
	});

	it('rejects a malformed authorization header', async () => {
		const res = await call('/auth', { headers: { authorization: `Basic ${OWNER}` } });
		expect(res.status).toBe(401);
	});

	it('the pipeline token is valid but cannot use owner routes', async () => {
		const res = await call('/auth', { token: PIPELINE });
		expect(res.status).toBe(403);
		expect((await res.json()) as object).toMatchObject({ error: { code: 'forbidden' } });
	});
});

describe('routing', () => {
	it('404 for unknown paths, before any auth', async () => {
		const res = await call('/nope', { token: OWNER });
		expect(res.status).toBe(404);
	});

	it('405 with Allow for a known path and the wrong method', async () => {
		const res = await call('/auth', { method: 'POST', token: OWNER });
		expect(res.status).toBe(405);
		expect(res.headers.get('allow')).toBe('GET, OPTIONS');
	});

	it('tolerates a trailing slash', async () => {
		expect((await call('/auth/', { token: OWNER })).status).toBe(204);
	});
});

describe('CORS', () => {
	it('echoes an allowed origin', async () => {
		const res = await call('/auth', { token: OWNER, origin: ORIGIN });
		expect(res.headers.get('access-control-allow-origin')).toBe(ORIGIN);
		expect(res.headers.get('vary')).toBe('Origin');
	});

	it('adds CORS headers to errors too, so the app can read them', async () => {
		const res = await call('/auth', { origin: ORIGIN });
		expect(res.status).toBe(401);
		expect(res.headers.get('access-control-allow-origin')).toBe(ORIGIN);
	});

	it('gives other origins no CORS headers', async () => {
		const res = await call('/auth', { token: OWNER, origin: 'https://evil.example' });
		expect(res.headers.get('access-control-allow-origin')).toBeNull();
	});

	it('answers preflight for allowed origins without auth', async () => {
		const res = await call('/auth', { method: 'OPTIONS', origin: 'http://localhost:5173' });
		expect(res.status).toBe(204);
		expect(res.headers.get('access-control-allow-origin')).toBe('http://localhost:5173');
		expect(res.headers.get('access-control-allow-headers')).toBe('authorization, content-type');
		expect(res.headers.get('access-control-allow-methods')).toContain('PUT');
	});

	it('preflight from other origins gets nothing the browser would accept', async () => {
		const res = await call('/auth', { method: 'OPTIONS', origin: 'https://evil.example' });
		expect(res.headers.get('access-control-allow-origin')).toBeNull();
	});
});

describe('rate limiting', () => {
	it('locks out an IP after 10 failed sign-ins, even for the right token', async () => {
		const ip = freshIp();
		for (let i = 0; i < 10; i++) {
			expect((await call('/auth', { token: 'wrong', ip })).status).toBe(401);
		}
		const locked = await call('/auth', { token: OWNER, ip });
		expect(locked.status).toBe(429);
		expect(locked.headers.get('retry-after')).toBe('60');
		// Other IPs are unaffected.
		expect((await call('/auth', { token: OWNER })).status).toBe(204);
	});

	it('limits requests per IP', async () => {
		const ip = freshIp();
		let last = 0;
		for (let i = 0; i < 121; i++) last = (await call('/nope', { ip })).status;
		expect(last).toBe(429);
	});
});
