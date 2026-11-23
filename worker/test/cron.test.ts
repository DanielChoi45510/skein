import {
	createExecutionContext,
	createScheduledController,
	env,
	waitOnExecutionContext
} from 'cloudflare:test';
import { afterEach, describe, expect, it } from 'vitest';
import worker from '../src/index';
import { backupTrigger, RECENT_MS, shouldDispatch } from '../src/cron';
import { mockGitHub, type GitHubMock } from './github-mock';

const NOW = Date.parse('2026-11-23T12:47:00Z');
const MIN = 60_000;
const run = (minutesAgo: number, status = 'completed', event = 'schedule') => ({
	created_at: new Date(NOW - minutesAgo * MIN).toISOString(),
	status,
	event
});

let gh: GitHubMock | undefined;
afterEach(() => gh?.restore());

describe('shouldDispatch', () => {
	it('stays quiet while GitHub\'s own :17 schedule works', () => {
		expect(shouldDispatch([run(30)], NOW)).toBe('ran-recently');
	});

	it("doesn't count its own dispatch an hour ago as recent", () => {
		expect(RECENT_MS).toBeLessThan(60 * MIN);
		expect(shouldDispatch([run(60, 'completed', 'workflow_dispatch')], NOW)).toBeNull();
	});

	it('skips while a run is queued or in progress, whatever its age', () => {
		expect(shouldDispatch([run(120, 'queued')], NOW)).toBe('run-active');
		expect(shouldDispatch([run(90, 'in_progress'), run(200)], NOW)).toBe('run-active');
	});

	it('dispatches when there are no runs at all', () => {
		expect(shouldDispatch([], NOW)).toBeNull();
	});
});

describe('backupTrigger', () => {
	it('dispatches when the last run is old', async () => {
		gh = mockGitHub({ runs: [run(75)] });
		expect(await backupTrigger(env, NOW)).toBe('dispatched');
		expect(gh.calls.map((c) => c.method)).toEqual(['GET', 'POST']);
		expect(gh.calls[0]!.url).toContain('/actions/workflows/pipeline.yml/runs?per_page=5');
	});

	it('does nothing when a run happened recently', async () => {
		gh = mockGitHub({ runs: [run(10)] });
		expect(await backupTrigger(env, NOW)).toBe('ran-recently');
		expect(gh.calls.map((c) => c.method)).toEqual(['GET']);
	});

	it('never dispatches blind when GitHub cannot list runs', async () => {
		gh = mockGitHub({ runs: 'fail' });
		expect(await backupTrigger(env, NOW)).toBe('github-unavailable');
		expect(gh.calls.map((c) => c.method)).toEqual(['GET']);
	});

	it('reports a refused dispatch', async () => {
		gh = mockGitHub({ runs: [], dispatchStatus: 422 });
		expect(await backupTrigger(env, NOW)).toBe('dispatch-failed');
	});

	it('is off without GitHub settings', async () => {
		gh = mockGitHub();
		expect(await backupTrigger({ ...env, GITHUB_REPO: undefined }, NOW)).toBe('not-configured');
		expect(gh.calls).toHaveLength(0);
	});
});

describe('scheduled handler', () => {
	it('runs the backup trigger', async () => {
		gh = mockGitHub({ runs: [] });
		const ctx = createExecutionContext();
		await worker.scheduled(createScheduledController({ cron: '47 * * * *' }), env, ctx);
		await waitOnExecutionContext(ctx);
		expect(gh.calls.map((c) => c.method)).toEqual(['GET', 'POST']);
	});
});
