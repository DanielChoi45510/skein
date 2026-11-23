<script lang="ts">
	// Owner-only header controls (DESIGN §9.2–9.3). Rendered only on a device with the
	// owner token, so visitors see nothing new.
	import { onDestroy } from 'svelte';
	import { resolve } from '$app/paths';
	import { waitLabel, WorkerError } from '$lib/owner';
	import { owner } from '$lib/owner.svelte';

	let sending = $state(false);
	let until = $state(0); // refresh cooldown end, ms
	let now = $state(Date.now());
	let status = $state<string | null>(null);

	const timer = setInterval(() => (now = Date.now()), 5000);
	onDestroy(() => clearInterval(timer));

	const wait = $derived(waitLabel(until, now));

	async function refresh() {
		sending = true;
		status = null;
		try {
			const res = await owner.call('/refresh', { method: 'POST' });
			const body = (await res.json()) as { next_allowed_at: string };
			until = Date.parse(body.next_allowed_at);
			status = 'Update started. The new feed shows up in about a minute.';
		} catch (e) {
			if (e instanceof WorkerError && e.kind === 'rate_limited' && e.retryAfter) {
				until = Date.now() + e.retryAfter * 1000;
			}
			status = e instanceof WorkerError ? e.message : 'Refresh failed.';
		}
		sending = false;
		now = Date.now();
	}
</script>

<div class="owner">
	<button type="button" onclick={refresh} disabled={sending || wait !== null}>
		{sending ? 'Starting…' : (wait ?? 'Refresh now')}
	</button>
	<a href={resolve('/settings/')}>Settings</a>
</div>
<p class="status" aria-live="polite">{status ?? ''}</p>

<style>
	.owner {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	button,
	a {
		display: inline-flex;
		align-items: center;
		min-height: 44px;
		padding: 0 0.8rem;
		border: 1px solid var(--border);
		border-radius: var(--radius);
		background: transparent;
		color: var(--muted);
		font-size: 0.9rem;
		text-decoration: none;
		cursor: pointer;
	}
	button:hover:not(:disabled),
	a:hover {
		color: var(--text);
	}
	button:disabled {
		cursor: default;
		opacity: 0.7;
	}
	.status {
		flex-basis: 100%;
		margin: 0;
		font-size: 0.85rem;
		color: var(--muted);
		text-align: right;
	}
	.status:empty {
		display: none;
	}
</style>
