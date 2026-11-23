// Owner read-state sync (DESIGN §9.2): this browser's topic and thread "last seen"
// stores, kept in step with the Worker's /read-state.
//
//   pull  GET /read-state, merged into the local stores (later instant wins). On
//         start, and when the tab comes back after PULL_AFTER_MS. If this browser
//         has anything newer than the server, it pushes right after.
//   push  PUT the whole local state; the Worker merges and returns the result,
//         which is merged back. Debounced after local changes; flushed with
//         `keepalive` when the tab is hidden, so it completes as the tab closes.
//
// Failures are quiet (offline, Worker down): local read state keeps working and the
// next pull/push catches up. A rejected token signs the device out (owner.call).

import {
	localReadState,
	mergeRemote,
	onReadStateChange,
	safeStorage,
	type ReadStateDoc,
	type Store
} from './readState';

export const PUSH_DEBOUNCE_MS = 3000;
export const PULL_AFTER_MS = 60_000;
const KEEPALIVE_MAX_BYTES = 60_000; // browsers cap keepalive bodies at 64 KB

export type Call = (path: string, init?: RequestInit) => Promise<Response>;

export class ReadSync {
	private timer: ReturnType<typeof setTimeout> | null = null;
	private pushing: Promise<void> | null = null;
	private dirty = false;
	private lastPull = -Infinity;
	private unsubscribe: (() => void) | null = null;

	constructor(
		private readonly call: Call,
		private readonly store: Store = safeStorage(),
		private readonly now: () => number = Date.now
	) {}

	/** Initial pull, then push local changes as they happen. Resolves after the pull. */
	async start(): Promise<void> {
		this.unsubscribe = onReadStateChange(() => this.schedule());
		await this.pull();
	}

	stop(): void {
		this.unsubscribe?.();
		this.unsubscribe = null;
		if (this.timer) clearTimeout(this.timer);
		this.timer = null;
	}

	async pull(): Promise<void> {
		this.lastPull = this.now();
		try {
			const res = await this.call('/read-state');
			const { ahead } = mergeRemote((await res.json()) as ReadStateDoc, this.store);
			if (ahead) await this.push();
		} catch {
			// quiet: local read state still works; the next pull catches up
		}
	}

	/** Pull again if the last pull is older than PULL_AFTER_MS (tab came back). */
	pullIfStale(): Promise<void> {
		return this.now() - this.lastPull >= PULL_AFTER_MS ? this.pull() : Promise.resolve();
	}

	schedule(): void {
		if (this.timer) clearTimeout(this.timer);
		this.timer = setTimeout(() => {
			this.timer = null;
			void this.push();
		}, PUSH_DEBOUNCE_MS);
	}

	/** Push now if a push is waiting (tab hidden or closing). */
	flush(): void {
		if (!this.timer) return;
		clearTimeout(this.timer);
		this.timer = null;
		void this.push({ keepalive: true });
	}

	async push({ keepalive = false } = {}): Promise<void> {
		if (this.pushing) {
			this.dirty = true; // push again once this one is done
			return this.pushing;
		}
		const body = JSON.stringify(localReadState(this.store));
		this.pushing = this.call('/read-state', {
			method: 'PUT',
			body,
			keepalive: keepalive && body.length < KEEPALIVE_MAX_BYTES
		})
			.then(async (res) => {
				mergeRemote((await res.json()) as ReadStateDoc, this.store);
			})
			.catch(() => {
				// quiet; the next change or pull retries
			})
			.finally(() => {
				this.pushing = null;
			});
		await this.pushing;
		if (this.dirty) {
			this.dirty = false;
			await this.push();
		}
	}
}
