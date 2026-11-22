// Re-fetch the feed every few minutes while the page is visible (DESIGN §9.3).
// No polling in background tabs; a tab that becomes visible refreshes if stale.

export const REFRESH_MS = 5 * 60_000;

interface Env {
	now: () => number;
	isVisible: () => boolean;
	setInterval: (fn: () => void, ms: number) => unknown;
	clearInterval: (handle: unknown) => void;
	onVisibilityChange: (fn: () => void) => () => void;
}

const browserEnv = (): Env => ({
	now: () => Date.now(),
	isVisible: () => document.visibilityState === 'visible',
	setInterval: (fn, ms) => window.setInterval(fn, ms),
	clearInterval: (h) => window.clearInterval(h as number),
	onVisibilityChange: (fn) => {
		document.addEventListener('visibilitychange', fn);
		return () => document.removeEventListener('visibilitychange', fn);
	}
});

/** Calls `refresh` every `ms` while visible. Returns a stop function. Doesn't call it immediately. */
export function poll(refresh: () => void, ms = REFRESH_MS, env: Env = browserEnv()): () => void {
	let last = env.now();
	const tick = () => {
		if (env.isVisible() && env.now() - last >= ms) {
			last = env.now();
			refresh();
		}
	};
	const handle = env.setInterval(tick, Math.min(ms, 60_000));
	const unlisten = env.onVisibilityChange(tick);
	return () => {
		env.clearInterval(handle);
		unlisten();
	};
}
