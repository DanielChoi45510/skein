/** Bindings and settings (wrangler.toml, `wrangler secret put`, or .dev.vars locally). */
export interface Env {
	SKEIN: KVNamespace;
	// Secrets. A missing one disables what it guards (fail closed).
	OWNER_TOKEN?: string;
	PIPELINE_TOKEN?: string;
	GITHUB_TOKEN?: string;
	// Per-deployment settings.
	ALLOWED_ORIGINS?: string; // comma-separated, e.g. https://<user>.github.io
	GITHUB_REPO?: string; // "owner/name"
	GITHUB_WORKFLOW?: string; // default pipeline.yml
	GITHUB_REF?: string; // default main
	// Optional Cloudflare rate-limiting binding (see wrangler.toml).
	RATE_LIMITER?: RateLimit;
}
