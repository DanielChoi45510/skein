// Reactive owner state shared by the layout, Settings and (later) owner controls.

import { callWorker, forgetToken, loadToken, ownerFeaturesAvailable, saveToken, WorkerError } from './owner';

class Owner {
	token = $state<string | null>(ownerFeaturesAvailable() ? loadToken() : null);
	/** Set when the Worker rejected the stored token, so Settings can say why. */
	rejected = $state(false);

	get signedIn(): boolean {
		return this.token !== null;
	}

	signIn(token: string): void {
		saveToken(token);
		this.token = token;
		this.rejected = false;
	}

	signOut(): void {
		forgetToken();
		this.token = null;
	}

	/** callWorker with the stored token; a 401 signs this device out. */
	async call(path: string, init: RequestInit = {}): Promise<Response> {
		if (!this.token) throw new WorkerError('unauthorized', 'Not signed in.');
		try {
			return await callWorker(path, this.token, init);
		} catch (e) {
			if (e instanceof WorkerError && e.kind === 'unauthorized') {
				this.signOut();
				this.rejected = true;
			}
			throw e;
		}
	}
}

export const owner = new Owner();

/** "Refresh now", shared by the header and the owner panels so the cooldown is one. */
class Refresher {
	sending = $state(false);
	until = $state(0); // cooldown end, ms
	status = $state<string | null>(null);

	async refresh(): Promise<void> {
		this.sending = true;
		this.status = null;
		try {
			const res = await owner.call('/refresh', { method: 'POST' });
			const body = (await res.json()) as { next_allowed_at: string };
			this.until = Date.parse(body.next_allowed_at);
			this.status = 'Update started. The new feed shows up in about a minute.';
		} catch (e) {
			if (e instanceof WorkerError && e.kind === 'rate_limited' && e.retryAfter) {
				this.until = Date.now() + e.retryAfter * 1000;
			}
			this.status = e instanceof WorkerError ? e.message : 'Refresh failed.';
		}
		this.sending = false;
	}
}

export const refresher = new Refresher();
