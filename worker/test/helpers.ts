import { SELF } from 'cloudflare:test';
import { TEST_ENV } from './env';

export const ORIGIN = 'https://owner.example.github.io';
export const OWNER = TEST_ENV.OWNER_TOKEN;
export const PIPELINE = TEST_ENV.PIPELINE_TOKEN;

let ipCounter = 0;
/** A fresh client IP per call, so per-IP limits in one test don't leak into another. */
export const freshIp = () => `203.0.113.${(ipCounter = (ipCounter % 250) + 1)}-${Math.random()}`;

export interface CallOptions {
	method?: string;
	token?: string;
	origin?: string;
	ip?: string;
	body?: unknown;
	headers?: Record<string, string>;
}

export function call(path: string, o: CallOptions = {}): Promise<Response> {
	const headers: Record<string, string> = { 'cf-connecting-ip': o.ip ?? freshIp(), ...o.headers };
	if (o.token) headers.authorization = `Bearer ${o.token}`;
	if (o.origin) headers.origin = o.origin;
	let body: string | undefined;
	if (o.body !== undefined) {
		body = typeof o.body === 'string' ? o.body : JSON.stringify(o.body);
		headers['content-type'] = 'application/json';
	}
	return SELF.fetch(`https://worker.test${path}`, { method: o.method ?? 'GET', headers, body });
}

/** Clear the test KV namespace: storage is shared between tests in a file. */
export async function resetKv(): Promise<void> {
	const { env } = await import('cloudflare:test');
	const { keys } = await env.SKEIN.list();
	await Promise.all(keys.map((k) => env.SKEIN.delete(k.name)));
}
