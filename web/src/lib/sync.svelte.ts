// Wires ReadSync to the owner token and the page lifecycle. Imported by the root
// layout, so the initial pull starts before any page reads its "last visit".

import { owner } from './owner.svelte';
import { ReadSync } from './readSync';

let sync: ReadSync | null = null;
let ready: Promise<void> = Promise.resolve();

function onVisibility() {
	if (!sync) return;
	if (document.visibilityState === 'hidden') sync.flush();
	else void sync.pullIfStale();
}

function onPageHide() {
	sync?.flush();
}

export function startOwnerSync(): void {
	if (sync || !owner.signedIn) return;
	sync = new ReadSync((path, init) => owner.call(path, init));
	ready = sync.start();
	document.addEventListener('visibilitychange', onVisibility);
	window.addEventListener('pagehide', onPageHide);
}

export function stopOwnerSync(): void {
	sync?.stop();
	sync = null;
	ready = Promise.resolve();
	document.removeEventListener('visibilitychange', onVisibility);
	window.removeEventListener('pagehide', onPageHide);
}

/**
 * Resolves once the first pull has merged the owner's synced read state (or after
 * `timeoutMs`, so a slow Worker never holds a page up). Immediate for visitors.
 */
export function readStateReady(timeoutMs = 2500): Promise<void> {
	return Promise.race([ready, new Promise<void>((r) => setTimeout(r, timeoutMs))]);
}

if (typeof window !== 'undefined') startOwnerSync();
