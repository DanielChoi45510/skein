// `env` from cloudflare:test has the Worker's bindings (KV, secrets, settings).
import type { Env as WorkerEnv } from '../src/env';

declare global {
	namespace Cloudflare {
		interface Env extends WorkerEnv {}
	}
}
