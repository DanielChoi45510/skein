// POST /refresh (DESIGN §9.3): the owner's "Refresh now" starts a pipeline run.
// A cooldown stops accidental double taps and loops from burning Actions time; the
// workflow's own concurrency group already keeps runs from overlapping.

import type { Context } from './index';
import { dispatch, githubConfig } from './github';
import { error, json } from './http';

export const LAST_REFRESH_KEY = 'refresh:last';
export const COOLDOWN_MS = 5 * 60 * 1000;

export async function postRefresh({ env }: Context): Promise<Response> {
	const cfg = githubConfig(env);
	if (!cfg) return error(503, 'unavailable', 'Refresh is not configured on this Worker.');

	const now = Date.now();
	const last = await env.SKEIN.get(LAST_REFRESH_KEY);
	const since = last ? now - Date.parse(last) : Infinity;
	if (since < COOLDOWN_MS) {
		const wait = Math.ceil((COOLDOWN_MS - since) / 1000);
		return error(429, 'rate_limited', `Refreshed recently. Try again in ${wait} s.`, {
			'retry-after': String(wait)
		});
	}

	const result = await dispatch(cfg);
	if (!result.ok) {
		console.warn('refresh: GitHub dispatch failed', result.status);
		return error(502, 'upstream_error', `GitHub refused the run (HTTP ${result.status}).`);
	}
	const at = new Date(now).toISOString();
	await env.SKEIN.put(LAST_REFRESH_KEY, at);
	return json(
		{ dispatched_at: at, next_allowed_at: new Date(now + COOLDOWN_MS).toISOString() },
		202
	);
}
