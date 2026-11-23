// Bearer-token auth (DESIGN §10.2). Two roles:
//   owner     OWNER_TOKEN: everything
//   pipeline  PIPELINE_TOKEN: GET /overrides only (an Actions secret, so it can't write)
// Tokens are compared as SHA-256 digests with a timing-safe comparison. A role
// whose secret isn't set can't be matched (fail closed).

import type { Env } from './env';

export type Role = 'owner' | 'pipeline';

const encoder = new TextEncoder();

async function digest(value: string): Promise<ArrayBuffer> {
	return crypto.subtle.digest('SHA-256', encoder.encode(value));
}

async function sameSecret(given: string, expected: string | undefined): Promise<boolean> {
	if (!expected) return false;
	const [a, b] = await Promise.all([digest(given), digest(expected)]);
	return crypto.subtle.timingSafeEqual(a, b);
}

export function bearer(request: Request): string | null {
	const header = request.headers.get('authorization') ?? '';
	const match = /^Bearer\s+(\S+)\s*$/i.exec(header);
	return match?.[1] ?? null;
}

/** The token's role, or null when it's missing or matches no configured secret. */
export async function authenticate(request: Request, env: Env): Promise<Role | null> {
	const token = bearer(request);
	if (!token) return null;
	// Check both, always, so timing doesn't reveal which secret matched.
	const [owner, pipeline] = await Promise.all([
		sameSecret(token, env.OWNER_TOKEN),
		sameSecret(token, env.PIPELINE_TOKEN)
	]);
	if (owner) return 'owner';
	if (pipeline) return 'pipeline';
	return null;
}
