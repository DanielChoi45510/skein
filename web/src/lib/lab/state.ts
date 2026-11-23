// Design lab (UI overhaul step 1): which direction, view and theme is shown.
// The state lives in the query string so any combination can be bookmarked or
// opened on a phone; the last choice is remembered per browser.

import type { Store } from '$lib/readState';

export const DIRECTIONS = ['broadsheet', 'ledger', 'pebble'] as const;
export const VIEWS = ['home', 'topic', 'thread'] as const;
export const THEMES = ['auto', 'dark', 'light'] as const;

export type Direction = (typeof DIRECTIONS)[number];
export type View = (typeof VIEWS)[number];
export type Theme = (typeof THEMES)[number];

export interface LabState {
	d: Direction;
	v: View;
	theme: Theme;
	topic: string | null; // topic view and thread view (the thread's topic)
	thread: string | null; // thread view
}

export const DEFAULT_STATE: LabState = {
	d: 'broadsheet',
	v: 'home',
	theme: 'auto',
	topic: null,
	thread: null
};

export const DIRECTION_NAMES: Record<Direction, string> = {
	broadsheet: 'Broadsheet',
	ledger: 'Ledger',
	pebble: 'Pebble'
};

const STORAGE_KEY = 'skein.lab.v1';
const KEYS = ['d', 'v', 'theme', 'topic', 'thread'] as const;

function oneOf<T extends string>(list: readonly T[], value: string | null, fallback: T): T {
	return list.includes(value as T) ? (value as T) : fallback;
}

export function parseState(params: URLSearchParams): LabState {
	return {
		d: oneOf(DIRECTIONS, params.get('d'), DEFAULT_STATE.d),
		v: oneOf(VIEWS, params.get('v'), DEFAULT_STATE.v),
		theme: oneOf(THEMES, params.get('theme'), DEFAULT_STATE.theme),
		topic: params.get('topic') || null,
		thread: params.get('thread') || null
	};
}

/** Query string (with "?") for a state; defaults and empty ids are left out. */
export function toQuery(state: LabState): string {
	const params = new URLSearchParams();
	for (const key of KEYS) {
		const value = state[key];
		if (value && value !== DEFAULT_STATE[key]) params.set(key, value);
	}
	const qs = params.toString();
	return qs ? `?${qs}` : '';
}

export const hasStateParams = (params: URLSearchParams) => KEYS.some((k) => params.has(k));

/** The remembered query string, or null. */
export function loadSaved(store: Store): string | null {
	try {
		const saved = store.getItem(STORAGE_KEY);
		return saved && saved.startsWith('?') ? toQuery(parseState(new URLSearchParams(saved))) : null;
	} catch {
		return null;
	}
}

export function save(store: Store, state: LabState): void {
	try {
		store.setItem(STORAGE_KEY, toQuery(state) || '?');
	} catch {
		// storage full or blocked: the lab still works, it just won't remember
	}
}
