import { createExecutionContext, env } from 'cloudflare:test';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { COOLDOWN_MS, LAST_REFRESH_KEY, postRefresh } from '../src/refresh';
import { mockGitHub, type GitHubMock } from './github-mock';
import { call, OWNER, PIPELINE, resetKv } from './helpers';

beforeEach(resetKv);

let gh: GitHubMock | undefined;
afterEach(() => gh?.restore());

describe('POST /refresh', () => {
	it('dispatches the pipeline workflow on main and starts the cooldown', async () => {
		gh = mockGitHub();
		const res = await call('/refresh', { method: 'POST', token: OWNER });
		expect(res.status).toBe(202);
		const body = (await res.json()) as { dispatched_at: string; next_allowed_at: string };
		expect(Date.parse(body.next_allowed_at) - Date.parse(body.dispatched_at)).toBe(COOLDOWN_MS);

		expect(gh.calls).toHaveLength(1);
		const [c] = gh.calls;
		expect(c!.method).toBe('POST');
		expect(c!.url).toBe(
			'https://api.github.com/repos/example/skein/actions/workflows/pipeline.yml/dispatches'
		);
		expect(JSON.parse(c!.body!)).toEqual({ ref: 'main' });
		expect(c!.headers.get('authorization')).toBe('Bearer test-github-token');
		expect(c!.headers.get('user-agent')).toBe('skein-owner-worker');
		expect(await env.SKEIN.get(LAST_REFRESH_KEY)).toBe(body.dispatched_at);
	});

	it('refuses a second refresh within the cooldown, without calling GitHub', async () => {
		gh = mockGitHub();
		await call('/refresh', { method: 'POST', token: OWNER });
		const again = await call('/refresh', { method: 'POST', token: OWNER });
		expect(again.status).toBe(429);
		const wait = Number(again.headers.get('retry-after'));
		expect(wait).toBeGreaterThan(290);
		expect(wait).toBeLessThanOrEqual(300);
		expect(gh.calls).toHaveLength(1);
	});

	it('allows a refresh once the cooldown has passed', async () => {
		gh = mockGitHub();
		await env.SKEIN.put(LAST_REFRESH_KEY, new Date(Date.now() - COOLDOWN_MS - 1000).toISOString());
		expect((await call('/refresh', { method: 'POST', token: OWNER })).status).toBe(202);
	});

	it('reports GitHub errors as 502 and keeps no cooldown', async () => {
		gh = mockGitHub({ dispatchStatus: 403 });
		const res = await call('/refresh', { method: 'POST', token: OWNER });
		expect(res.status).toBe(502);
		const text = await res.text();
		expect(text).toContain('HTTP 403');
		expect(text).not.toContain('test-github-token');
		expect(await env.SKEIN.get(LAST_REFRESH_KEY)).toBeNull();
	});

	it('is 503 when the Worker has no GitHub settings', async () => {
		gh = mockGitHub();
		const res = await postRefresh({
			request: new Request('https://worker.test/refresh', { method: 'POST' }),
			env: { ...env, GITHUB_TOKEN: undefined },
			ctx: createExecutionContext(),
			role: 'owner'
		});
		expect(res.status).toBe(503);
		expect(gh.calls).toHaveLength(0);
	});

	it('is owner-only', async () => {
		gh = mockGitHub();
		expect((await call('/refresh', { method: 'POST' })).status).toBe(401);
		expect((await call('/refresh', { method: 'POST', token: PIPELINE })).status).toBe(403);
		expect(gh.calls).toHaveLength(0);
	});
});
