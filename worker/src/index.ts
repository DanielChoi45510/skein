// Skein owner API (DESIGN §10.2): one Worker + KV for the site owner.
//
// Every request: CORS preflight → per-IP request limit → route → failed-auth
// lockout → bearer token → role check → handler. Responses are JSON (or empty),
// never cached, and carry CORS headers only for ALLOWED_ORIGINS. Requests with no
// Origin (curl, the pipeline) are fine: CORS only restricts browsers; the token is
// what protects every route.

import { authenticate, type Role } from './auth';
import type { Env } from './env';
import { corsHeaders, empty, error, withCors } from './http';
import { AUTH_FAILURE_LIMIT, FixedWindow, REQUEST_LIMIT } from './limiter';
import { getReadState, putReadState } from './readState';

export interface Context {
	request: Request;
	env: Env;
	ctx: ExecutionContext;
	role: Role;
}

export interface Route {
	method: 'GET' | 'PUT' | 'POST';
	path: string;
	roles: readonly Role[];
	handler: (c: Context) => Response | Promise<Response>;
}

export const routes: Route[] = [
	// Lets the Settings screen check a pasted token without side effects.
	{ method: 'GET', path: '/auth', roles: ['owner'], handler: () => empty(204) },
	{ method: 'GET', path: '/read-state', roles: ['owner'], handler: getReadState },
	{ method: 'PUT', path: '/read-state', roles: ['owner'], handler: putReadState }
];

// Per Worker instance (see limiter.ts).
const requests = new FixedWindow(REQUEST_LIMIT);
const authFailures = new FixedWindow(AUTH_FAILURE_LIMIT);
const RETRY_AFTER = { 'retry-after': '60' };

async function underRequestLimit(env: Env, ip: string): Promise<boolean> {
	if (env.RATE_LIMITER) return (await env.RATE_LIMITER.limit({ key: ip })).success;
	return requests.hit(ip);
}

async function handle(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
	if (request.method === 'OPTIONS') return empty(204);

	const ip = request.headers.get('cf-connecting-ip') ?? 'unknown';
	if (!(await underRequestLimit(env, ip))) {
		return error(429, 'rate_limited', 'Too many requests. Try again in a minute.', RETRY_AFTER);
	}

	const path = new URL(request.url).pathname.replace(/\/+$/, '') || '/';
	const candidates = routes.filter((r) => r.path === path);
	if (!candidates.length) return error(404, 'not_found', 'No such endpoint.');
	const route = candidates.find((r) => r.method === request.method);
	if (!route) {
		const allow = [...candidates.map((r) => r.method), 'OPTIONS'].join(', ');
		return error(405, 'method_not_allowed', `Use ${allow}.`, { allow });
	}

	if (authFailures.blocked(ip)) {
		return error(429, 'rate_limited', 'Too many failed sign-ins. Try again in a minute.', RETRY_AFTER);
	}
	const role = await authenticate(request, env);
	if (!role) {
		authFailures.hit(ip);
		return error(401, 'unauthorized', 'Missing or invalid token.', {
			'www-authenticate': 'Bearer'
		});
	}
	if (!route.roles.includes(role)) {
		return error(403, 'forbidden', 'This token cannot do that.');
	}
	return route.handler({ request, env, ctx, role });
}

export default {
	async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
		const cors = corsHeaders(request, env.ALLOWED_ORIGINS);
		try {
			return withCors(await handle(request, env, ctx), cors);
		} catch (e) {
			// Never echo internals (or anything secret) to the client.
			console.error('unhandled error', e instanceof Error ? e.name : typeof e);
			return withCors(error(500, 'internal', 'Something went wrong.'), cors);
		}
	}
} satisfies ExportedHandler<Env>;
