import { describe, expect, it } from 'vitest';
import {
	cleanTitle,
	getOverrides,
	MAX_SPLIT_ITEMS,
	MAX_TITLE,
	moveItems,
	postOverride,
	problem,
	splitThread,
	type OverrideAction,
	type OverridesDoc
} from './overridesClient';

/** A fake Worker that applies actions like worker/src/overrides.ts does (enough of it). */
function fakeWorker() {
	const doc: OverridesDoc = { version: 1, updated_at: null, threads: {}, ops: [] };
	const sent: OverrideAction[] = [];
	let n = 0;
	const call = async (path: string, init: RequestInit = {}) => {
		if (path !== '/overrides') throw new Error(`unexpected ${path}`);
		if (init.method === 'POST') {
			const a = JSON.parse(init.body as string) as OverrideAction;
			sent.push(a);
			const at = `2026-11-23T12:00:0${n}Z`;
			if (a.action === 'rename') doc.threads[a.thread] = { ...doc.threads[a.thread], title: a.title ?? undefined };
			if (a.action === 'pin') doc.threads[a.thread] = { ...doc.threads[a.thread], pinned: true };
			if (a.action === 'split') doc.ops.push({ id: `op${n}`, at, type: 'split', thread: a.thread, items: a.items, new_id: `unew${n}` });
			if (a.action === 'move') doc.ops.push({ id: `op${n}`, at, type: 'move', item: a.item, to: a.to });
			n++;
		}
		return new Response(JSON.stringify(doc));
	};
	return { call, sent, doc };
}

describe('cleanTitle and problem', () => {
	it('tidies titles; empty means automatic', () => {
		expect(cleanTitle('  Ukraine   war ')).toBe('Ukraine war');
		expect(cleanTitle('   ')).toBeNull();
	});

	it.each<[OverrideAction, string | null]>([
		[{ action: 'rename', thread: 't', title: 'x'.repeat(MAX_TITLE) }, null],
		[{ action: 'rename', thread: 't', title: 'x'.repeat(MAX_TITLE + 1) }, 'at most'],
		[{ action: 'rename', thread: 't', title: null }, null],
		[{ action: 'merge', from: 't', into: 't' }, 'different thread'],
		[{ action: 'split', thread: 't', items: [] }, 'at least one'],
		[{ action: 'split', thread: 't', items: Array.from({ length: MAX_SPLIT_ITEMS + 1 }, (_, i) => `i${i}`) }, 'at most'],
		[{ action: 'move', item: 'i', to: 't' }, null]
	])('%j → %s', (action, expected) => {
		const p = problem(action);
		if (expected === null) expect(p).toBeNull();
		else expect(p).toContain(expected);
	});
});

describe('requests', () => {
	it('posts one action and returns the document', async () => {
		const w = fakeWorker();
		const doc = await postOverride(w.call, { action: 'pin', thread: 't1' });
		expect(doc.threads).toEqual({ t1: { pinned: true } });
		expect(await getOverrides(w.call)).toEqual(doc);
	});

	it('never sends an invalid action', async () => {
		const w = fakeWorker();
		await expect(postOverride(w.call, { action: 'merge', from: 'a', into: 'a' })).rejects.toThrow('different thread');
		expect(w.sent).toEqual([]);
	});

	it('split with a title renames the new thread by the id the Worker gave it', async () => {
		const w = fakeWorker();
		const doc = await splitThread(w.call, 't1', ['a', 'b'], 'Kerch bridge strikes');
		expect(w.sent).toEqual([
			{ action: 'split', thread: 't1', items: ['a', 'b'] },
			{ action: 'rename', thread: 'unew0', title: 'Kerch bridge strikes' }
		]);
		expect(doc.threads.unew0).toEqual({ title: 'Kerch bridge strikes' });
	});

	it('split without a title sends only the split', async () => {
		const w = fakeWorker();
		await splitThread(w.call, 't1', ['a'], null);
		expect(w.sent.map((a) => a.action)).toEqual(['split']);
	});

	it('moves several items one op each, in order', async () => {
		const w = fakeWorker();
		await moveItems(w.call, ['a', 'b'], 't2');
		expect(w.sent).toEqual([
			{ action: 'move', item: 'a', to: 't2' },
			{ action: 'move', item: 'b', to: 't2' }
		]);
		await expect(moveItems(w.call, [], 't2')).rejects.toThrow('at least one');
	});
});
