// Owner overrides from the app (DESIGN §10.2 "Overrides"): request bodies for
// POST /overrides, checked here with the Worker's own limits so mistakes get a
// message before a round trip. Every change takes effect on the next pipeline run.

export const MAX_TITLE = 120;
export const MAX_SPLIT_ITEMS = 50;

export type OverrideAction =
	| { action: 'rename'; thread: string; title: string | null }
	| { action: 'pin' | 'unpin' | 'mute' | 'unmute'; thread: string }
	| { action: 'merge'; from: string; into: string }
	| { action: 'split'; thread: string; items: string[] }
	| { action: 'move'; item: string; to: string };

export interface ThreadSettings {
	title?: string;
	pinned?: true;
	muted?: true;
}

export interface OverridesDoc {
	version: 1;
	updated_at: string | null;
	threads: Record<string, ThreadSettings>;
	ops: ({ id: string; at: string; type: string } & Record<string, unknown>)[];
}

/** Collapse whitespace; null for an empty title (back to the automatic title). */
export function cleanTitle(raw: string): string | null {
	const title = raw.replace(/\s+/g, ' ').trim();
	return title ? title : null;
}

/** A user-facing problem with the action, or null if it's fine to send. */
export function problem(a: OverrideAction): string | null {
	switch (a.action) {
		case 'rename':
			return a.title !== null && a.title.length > MAX_TITLE
				? `Titles can be at most ${MAX_TITLE} characters.`
				: null;
		case 'merge':
			return a.from === a.into ? 'Pick a different thread to merge into.' : null;
		case 'split':
			if (!a.items.length) return 'Select at least one story.';
			return a.items.length > MAX_SPLIT_ITEMS
				? `Split at most ${MAX_SPLIT_ITEMS} stories at a time.`
				: null;
		default:
			return null;
	}
}

type Call = (path: string, init?: RequestInit) => Promise<Response>;

export async function getOverrides(call: Call): Promise<OverridesDoc> {
	return (await (await call('/overrides')).json()) as OverridesDoc;
}

export async function postOverride(call: Call, action: OverrideAction): Promise<OverridesDoc> {
	const issue = problem(action);
	if (issue) throw new Error(issue);
	const res = await call('/overrides', { method: 'POST', body: JSON.stringify(action) });
	return (await res.json()) as OverridesDoc;
}

/**
 * Split `items` out of `thread`, then name the new thread if a title was given.
 * The Worker assigns the new thread's id; renames apply by id at export, so the
 * title takes effect when the pipeline creates the thread.
 */
export async function splitThread(
	call: Call,
	thread: string,
	items: string[],
	title: string | null
): Promise<OverridesDoc> {
	const doc = await postOverride(call, { action: 'split', thread, items });
	const op = [...doc.ops].reverse().find((o) => o.type === 'split' && o.thread === thread);
	const newId = op?.new_id;
	if (!title || typeof newId !== 'string') return doc;
	return postOverride(call, { action: 'rename', thread: newId, title });
}

/** Move each item to `to`, one op per item, in order. */
export async function moveItems(call: Call, items: string[], to: string): Promise<OverridesDoc> {
	let doc: OverridesDoc | null = null;
	for (const item of items) doc = await postOverride(call, { action: 'move', item, to });
	if (!doc) throw new Error('Select at least one story.');
	return doc;
}
