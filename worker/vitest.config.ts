import { cloudflareTest } from '@cloudflare/vitest-plugin';
import { defineConfig } from 'vitest/config';
import { TEST_ENV } from './test/env.ts';

// Tests run inside workerd (Miniflare) with local KV and test-only settings.
export default defineConfig({
	plugins: [
		cloudflareTest({
			wrangler: { configPath: './wrangler.toml' },
			miniflare: { bindings: TEST_ENV }
		})
	]
});
