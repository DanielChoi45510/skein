// Hourly backup trigger (wrangler.toml [triggers]; DESIGN §10.2). GitHub's own
// `schedule` trigger can be late or skipped, so at :47 the Worker checks the
// pipeline's recent runs and dispatches one only if
//   - none is queued or running, and
//   - none started in the last RECENT_MS (50 min).
// 50 min, not 60+: the Worker's own dispatch an hour earlier must not count as
// recent, or it would skip every other hour. A GitHub-scheduled run at :17 is 30
// min old at :47, so the backup stays quiet while GitHub's schedule works.

import type { Env } from './env';
import { dispatch, githubConfig, recentRuns, type WorkflowRun } from './github';

export const RECENT_MS = 50 * 60 * 1000;
const ACTIVE = new Set(['queued', 'in_progress', 'waiting', 'requested', 'pending']);

export type BackupDecision =
	| 'not-configured'
	| 'github-unavailable'
	| 'run-active'
	| 'ran-recently'
	| 'dispatched'
	| 'dispatch-failed';

export function shouldDispatch(runs: WorkflowRun[], now: number): 'run-active' | 'ran-recently' | null {
	if (runs.some((r) => ACTIVE.has(r.status))) return 'run-active';
	const newest = Math.max(...runs.map((r) => Date.parse(r.created_at)), -Infinity);
	return now - newest < RECENT_MS ? 'ran-recently' : null;
}

export async function backupTrigger(env: Env, now = Date.now()): Promise<BackupDecision> {
	const cfg = githubConfig(env);
	if (!cfg) return 'not-configured';
	const runs = await recentRuns(cfg);
	if (runs === null) return 'github-unavailable';
	const skip = shouldDispatch(runs, now);
	if (skip) return skip;
	return (await dispatch(cfg)).ok ? 'dispatched' : 'dispatch-failed';
}
