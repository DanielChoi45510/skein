// Test-only settings, shared by vitest.config.ts and the tests. Plain data: tests
// run inside workerd and must not import the Node-side Vitest config.
export const TEST_ENV = {
	OWNER_TOKEN: 'test-owner-token-0123456789abcdef',
	PIPELINE_TOKEN: 'test-pipeline-token-0123456789abcdef',
	GITHUB_TOKEN: 'test-github-token',
	ALLOWED_ORIGINS: 'https://owner.example.github.io,http://localhost:5173',
	GITHUB_REPO: 'example/skein'
};
