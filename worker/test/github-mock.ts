import { vi } from 'vitest';

export interface GitHubMock {
	calls: { url: string; method: string; headers: Headers; body: string | null }[];
	restore: () => void;
}

/** Stub GitHub's API: `runs` for the runs listing, `dispatchStatus` for dispatches. */
export function mockGitHub(
	opts: { runs?: unknown[] | 'fail'; dispatchStatus?: number } = {}
): GitHubMock {
	const calls: GitHubMock['calls'] = [];
	const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
		const req = new Request(input as RequestInfo, init);
		const body = req.method === 'GET' ? null : await req.text();
		calls.push({ url: req.url, method: req.method, headers: req.headers, body });
		if (!req.url.startsWith('https://api.github.com/')) throw new Error(`unexpected fetch ${req.url}`);
		if (req.url.endsWith('/dispatches')) return new Response(null, { status: opts.dispatchStatus ?? 204 });
		if (req.url.includes('/runs')) {
			if (opts.runs === 'fail') return new Response('{}', { status: 500 });
			return Response.json({ total_count: 0, workflow_runs: opts.runs ?? [] });
		}
		return new Response(null, { status: 404 });
	});
	return { calls, restore: () => spy.mockRestore() };
}
