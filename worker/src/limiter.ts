// Basic per-IP rate limiting (DESIGN §10.2).
//
// The default is an in-memory fixed window per Worker instance: free and needs no
// setup, but best-effort (each instance counts on its own, and an instance can be
// recycled). With 256-bit tokens, brute force is out of reach anyway; this mainly
// keeps noise and accidental loops cheap. If the optional RATE_LIMITER binding is
// configured (wrangler.toml), it's used for the general request limit instead.
// KV is never used for counters: it's eventually consistent and has a small free
// write quota.

export interface WindowLimit {
	limit: number;
	periodMs: number;
}

export class FixedWindow {
	private readonly counts = new Map<string, { start: number; count: number }>();

	constructor(
		private readonly rule: WindowLimit,
		private readonly now: () => number = Date.now
	) {}

	/** Count one hit for `key`; false when it's over the limit for this window. */
	hit(key: string): boolean {
		const t = this.now();
		const entry = this.counts.get(key);
		if (!entry || t - entry.start >= this.rule.periodMs) {
			this.counts.set(key, { start: t, count: 1 });
			this.sweep(t);
			return true;
		}
		entry.count += 1;
		return entry.count <= this.rule.limit;
	}

	/** Whether `key` is already over the limit, without counting a hit. */
	blocked(key: string): boolean {
		const entry = this.counts.get(key);
		return !!entry && this.now() - entry.start < this.rule.periodMs && entry.count >= this.rule.limit;
	}

	/** Drop expired windows now and then, so the map stays small. */
	private sweep(t: number): void {
		if (this.counts.size < 1000) return;
		for (const [k, v] of this.counts) {
			if (t - v.start >= this.rule.periodMs) this.counts.delete(k);
		}
	}
}

export const REQUEST_LIMIT: WindowLimit = { limit: 120, periodMs: 60_000 };
export const AUTH_FAILURE_LIMIT: WindowLimit = { limit: 10, periodMs: 60_000 };
