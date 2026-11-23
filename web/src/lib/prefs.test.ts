import { describe, expect, it } from 'vitest';
import { loadThreadOrder, saveThreadOrder } from './prefs';

function memoryStore() {
	const data = new Map<string, string>();
	return {
		data,
		getItem: (k: string) => data.get(k) ?? null,
		setItem: (k: string, v: string) => void data.set(k, v)
	};
}

describe('thread order preference', () => {
	it('defaults to newest first and remembers the choice', () => {
		const store = memoryStore();
		expect(loadThreadOrder(store)).toBe('newest');
		saveThreadOrder('chronological', store);
		expect(loadThreadOrder(store)).toBe('chronological');
	});

	it('falls back to newest first on unknown or unreadable values', () => {
		const store = memoryStore();
		store.data.set('skein.threadOrder.v1', 'sideways');
		expect(loadThreadOrder(store)).toBe('newest');
		const broken = {
			getItem: () => {
				throw new Error('blocked');
			},
			setItem: () => {
				throw new Error('blocked');
			}
		};
		expect(loadThreadOrder(broken)).toBe('newest');
		expect(() => saveThreadOrder('chronological', broken)).not.toThrow();
	});
});
