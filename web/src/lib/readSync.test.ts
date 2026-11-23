import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PULL_AFTER_MS, PUSH_DEBOUNCE_MS, ReadSync } from './readSync';
import {
	isAhead,
	localReadState,
	markSeen,
	markThreadSeen,
	mergeRemote,
	mergeSeen,
	onReadStateChange,
	type ReadStateDoc
} from './readState';

function memoryStore() {
	const data = new Map<string, string>();
	return { data, getItem: (k: string) => data.get(k) ?? null, setItem: (k: string, v: string) => void data.set(k, v) };
}

const T = (h: number) => `2026-11-23T${String(h).padStart(2, '0')}:00:00.000Z`;

describe('merge helpers', () => {
	it('mergeSeen keeps the later instant per id', () => {
		expect(mergeSeen({ a: T(10), b: T(12) }, { a: T(11), b: T(9), c: T(8), d: 'junk' })).toEqual({
			a: T(11),
			b: T(12),
			c: T(8)
		});
	});

	it('isAhead: local has something the server lacks or has older', () => {
		expect(isAhead({ a: T(10) }, { a: T(10) })).toBe(false);
		expect(isAhead({ a: T(11) }, { a: T(10) })).toBe(true);
		expect(isAhead({ b: T(1) }, { a: T(10) })).toBe(true);
		expect(isAhead({}, { a: T(10) })).toBe(false);
	});

	it('mergeRemote updates both stores and reports whether to push', () => {
		const store = memoryStore();
		markSeen('world', T(10), store);
		markThreadSeen('t1', T(9), store);
		const { ahead } = mergeRemote({ topics: { world: T(8), politics: T(7) }, threads: { t1: T(11) } }, store);
		expect(localReadState(store)).toEqual({
			topics: { world: T(10), politics: T(7) },
			threads: { t1: T(11) }
		});
		expect(ahead).toBe(true); // world is newer here
	});

	it('local marks notify listeners; remote merges do not', () => {
		const store = memoryStore();
		const seen = vi.fn();
		const off = onReadStateChange(seen);
		markSeen('world', T(10), store);
		markSeen('world', T(9), store); // backwards: no change, no call
		mergeRemote({ topics: { politics: T(1) }, threads: {} }, store);
		off();
		markSeen('world', T(11), store);
		expect(seen).toHaveBeenCalledTimes(1);
	});
});

class FakeWorker {
	state: ReadStateDoc = { topics: {}, threads: {} };
	calls: { path: string; method: string; body?: ReadStateDoc; keepalive?: boolean }[] = [];
	fail = false;

	call = async (path: string, init: RequestInit = {}): Promise<Response> => {
		const method = init.method ?? 'GET';
		const body = init.body ? (JSON.parse(init.body as string) as ReadStateDoc) : undefined;
		this.calls.push({ path, method, body, keepalive: init.keepalive });
		if (this.fail) throw new Error('offline');
		if (method === 'PUT' && body) {
			this.state = {
				topics: mergeSeen(this.state.topics, body.topics),
				threads: mergeSeen(this.state.threads, body.threads)
			};
		}
		return new Response(JSON.stringify(this.state));
	};
}

describe('ReadSync', () => {
	let worker: FakeWorker;
	let store: ReturnType<typeof memoryStore>;
	let sync: ReadSync;
	let now = 0;

	beforeEach(() => {
		vi.useFakeTimers();
		worker = new FakeWorker();
		store = memoryStore();
		now = 0;
		sync = new ReadSync(worker.call, store, () => now);
	});
	afterEach(() => {
		sync.stop();
		vi.useRealTimers();
	});

	it("start pulls the other devices' reading into this browser", async () => {
		worker.state = { topics: { world: T(10) }, threads: { t1: T(10) } };
		await sync.start();
		expect(localReadState(store)).toEqual(worker.state);
		expect(worker.calls.map((c) => c.method)).toEqual(['GET']); // nothing newer here: no push
	});

	it('pushes right after the pull when this browser is ahead', async () => {
		markSeen('world', T(12), store);
		worker.state = { topics: { world: T(10) }, threads: {} };
		await sync.start();
		expect(worker.calls.map((c) => c.method)).toEqual(['GET', 'PUT']);
		expect(worker.state.topics.world).toBe(T(12));
	});

	it('debounces local changes into one push', async () => {
		await sync.start();
		markSeen('world', T(10), store);
		markThreadSeen('t1', T(10), store);
		markSeen('politics', T(11), store);
		expect(worker.calls).toHaveLength(1); // only the pull so far
		await vi.advanceTimersByTimeAsync(PUSH_DEBOUNCE_MS);
		const puts = worker.calls.filter((c) => c.method === 'PUT');
		expect(puts).toHaveLength(1);
		expect(puts[0]!.body).toEqual({ topics: { world: T(10), politics: T(11) }, threads: { t1: T(10) } });
	});

	it('flush sends a pending push at once, with keepalive', async () => {
		await sync.start();
		markSeen('world', T(10), store);
		sync.flush();
		await vi.advanceTimersByTimeAsync(0);
		const [put] = worker.calls.filter((c) => c.method === 'PUT');
		expect(put!.keepalive).toBe(true);
		sync.flush(); // nothing pending: no call
		await vi.advanceTimersByTimeAsync(PUSH_DEBOUNCE_MS);
		expect(worker.calls.filter((c) => c.method === 'PUT')).toHaveLength(1);
	});

	it('never runs two pushes at once; a change during a push is sent after it', async () => {
		await sync.start();
		markSeen('world', T(10), store);
		const first = sync.push();
		markSeen('politics', T(11), store);
		const second = sync.push();
		await Promise.all([first, second]);
		const puts = worker.calls.filter((c) => c.method === 'PUT');
		expect(puts).toHaveLength(2);
		expect(puts[1]!.body!.topics).toEqual({ world: T(10), politics: T(11) });
	});

	it('pulls again only when the last pull is stale', async () => {
		await sync.start();
		now = PULL_AFTER_MS - 1;
		await sync.pullIfStale();
		now = PULL_AFTER_MS;
		await sync.pullIfStale();
		expect(worker.calls.filter((c) => c.method === 'GET')).toHaveLength(2);
	});

	it('stays quiet when the Worker is unreachable; local state is untouched', async () => {
		worker.fail = true;
		markSeen('world', T(10), store);
		await expect(sync.start()).resolves.toBeUndefined();
		await expect(sync.push()).resolves.toBeUndefined();
		expect(localReadState(store).topics).toEqual({ world: T(10) });
	});

	it('stop unsubscribes from local changes', async () => {
		await sync.start();
		sync.stop();
		markSeen('world', T(10), store);
		await vi.advanceTimersByTimeAsync(PUSH_DEBOUNCE_MS);
		expect(worker.calls.filter((c) => c.method === 'PUT')).toHaveLength(0);
	});
});
