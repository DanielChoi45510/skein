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
