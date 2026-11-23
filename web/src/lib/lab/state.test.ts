import { describe, expect, it } from 'vitest';
import { DEFAULT_STATE, hasStateParams, loadSaved, parseState, save, toQuery } from './state';

function memStore() {
	const m = new Map<string, string>();
	return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) };
}

describe('lab state', () => {
	it('falls back to defaults for missing or unknown values', () => {
		expect(parseState(new URLSearchParams(''))).toEqual(DEFAULT_STATE);
		expect(parseState(new URLSearchParams('d=comic&v=feed&theme=neon'))).toEqual(DEFAULT_STATE);
	});

	it('round-trips through the query string, leaving defaults out', () => {
		const s = { d: 'pebble', v: 'thread', theme: 'light', topic: 'world', thread: 't1' } as const;
		expect(parseState(new URLSearchParams(toQuery(s)))).toEqual(s);
		expect(toQuery(DEFAULT_STATE)).toBe('');
		expect(toQuery({ ...DEFAULT_STATE, d: 'ledger' })).toBe('?d=ledger');
	});

	it('knows whether a URL carries lab state', () => {
		expect(hasStateParams(new URLSearchParams('d=ledger'))).toBe(true);
		expect(hasStateParams(new URLSearchParams('x=1'))).toBe(false);
	});

	it('remembers the last choice, normalized', () => {
		const store = memStore();
		expect(loadSaved(store)).toBeNull();
		save(store, { ...DEFAULT_STATE, d: 'ledger', v: 'topic', topic: 'world' });
		expect(loadSaved(store)).toBe('?d=ledger&v=topic&topic=world');
		store.setItem('skein.lab.v1', 'garbage');
		expect(loadSaved(store)).toBeNull();
	});
});
