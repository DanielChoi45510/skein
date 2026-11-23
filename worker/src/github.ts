// GitHub Actions API calls for the pipeline workflow (DESIGN §9.3, §10.2), using a
// fine-grained token (GITHUB_TOKEN secret) limited to this repo with Actions read/write.
// Errors report the HTTP status only; neither the token nor GitHub's body is echoed.

import type { Env } from './env';

const API = 'https://api.github.com';

export interface GitHubConfig {
	token: string;
	repo: string; // owner/name
	workflow: string; // file name, e.g. pipeline.yml
	ref: string;
}

export interface WorkflowRun {
	created_at: string;
	status: string; // queued | in_progress | completed | waiting | requested | pending
	event: string; // schedule | workflow_dispatch | ...
}

/** Null when the deployment isn't configured for GitHub (refresh and the cron are then off). */
export function githubConfig(env: Env): GitHubConfig | null {
	const repo = env.GITHUB_REPO?.trim();
	if (!env.GITHUB_TOKEN || !repo || !/^[\w.-]+\/[\w.-]+$/.test(repo)) return null;
	return {
		token: env.GITHUB_TOKEN,
		repo,
		workflow: env.GITHUB_WORKFLOW || 'pipeline.yml',
		ref: env.GITHUB_REF || 'main'
	};
}

function headers(cfg: GitHubConfig): HeadersInit {
	return {
		authorization: `Bearer ${cfg.token}`,
		accept: 'application/vnd.github+json',
		'x-github-api-version': '2022-11-28',
		'user-agent': 'skein-owner-worker'
	};
}

const workflowUrl = (cfg: GitHubConfig) =>
	`${API}/repos/${cfg.repo}/actions/workflows/${encodeURIComponent(cfg.workflow)}`;

/** Start a pipeline run (workflow_dispatch). */
export async function dispatch(cfg: GitHubConfig): Promise<{ ok: true } | { ok: false; status: number }> {
	const res = await fetch(`${workflowUrl(cfg)}/dispatches`, {
		method: 'POST',
		headers: { ...headers(cfg), 'content-type': 'application/json' },
		body: JSON.stringify({ ref: cfg.ref })
	});
	return res.ok ? { ok: true } : { ok: false, status: res.status };
}

/** The workflow's most recent runs, newest first; null if GitHub didn't answer. */
export async function recentRuns(cfg: GitHubConfig, count = 5): Promise<WorkflowRun[] | null> {
	const res = await fetch(`${workflowUrl(cfg)}/runs?per_page=${count}`, { headers: headers(cfg) });
	if (!res.ok) return null;
	const data = (await res.json()) as { workflow_runs?: WorkflowRun[] };
	return (data.workflow_runs ?? []).filter((r) => typeof r.created_at === 'string');
}
