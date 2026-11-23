import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

// The owner Worker (DESIGN §10.2), baked in at build time like BASE_PATH. Unset
// (CI, forks, local dev without a Worker): owner features stay off entirely.
const env = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env;
const workerUrl = (env?.PUBLIC_WORKER_URL ?? '').trim().replace(/\/+$/, '');
if (workerUrl && !/^(https:\/\/[^/\s]+|http:\/\/localhost(:\d+)?)$/.test(workerUrl)) {
	throw new Error(`PUBLIC_WORKER_URL must look like "https://name.sub.workers.dev", got "${workerUrl}"`);
}

export default defineConfig({
	plugins: [sveltekit()],
	define: { __WORKER_URL__: JSON.stringify(workerUrl) },
	test: {
		include: ['src/**/*.test.ts'],
		environment: 'node'
	}
});
