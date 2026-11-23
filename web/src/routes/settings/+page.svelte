<script lang="ts">
	import { resolve } from '$app/paths';
	import { cleanToken, ownerFeaturesAvailable, verifyToken } from '$lib/owner';
	import { owner } from '$lib/owner.svelte';

	// Reached by URL only (bookmark it): visitors see no link to it.
	let input = $state('');
	let checking = $state(false);
	let message = $state<string | null>(null);
	let isError = $state(false);

	const MESSAGES = {
		invalid: "That token wasn't accepted. Check you pasted the owner token, not the pipeline token.",
		rate_limited: 'Too many attempts. Wait a minute and try again.',
		unreachable: "Couldn't reach the owner service. Check your connection.",
		failed: 'Something went wrong checking the token. Try again.'
	} as const;

	async function save(event: SubmitEvent) {
		event.preventDefault();
		const token = cleanToken(input);
		if (!token) return;
		checking = true;
		message = null;
		const result = await verifyToken(token);
		checking = false;
		if (result === 'ok') {
			owner.signIn(token);
			input = '';
			isError = false;
			message = 'Saved. This device now has owner access.';
		} else {
			isError = true;
			message = MESSAGES[result];
		}
	}

	function forget() {
		owner.signOut();
		isError = false;
		message = 'Forgotten. This device is back to visitor mode.';
	}
</script>

<svelte:head>
	<title>Settings · Skein</title>
	<meta name="robots" content="noindex" />
</svelte:head>

<nav><a href={resolve('/')}>← All topics</a></nav>

<h1>Settings</h1>

{#if !ownerFeaturesAvailable()}
	<p class="muted">Owner features aren't set up on this site.</p>
{:else if owner.signedIn}
	<section aria-labelledby="owner">
		<h2 id="owner">Owner access</h2>
		<p>This device has the owner token. Read state syncs across your devices, and owner controls are shown.</p>
		<button type="button" class="secondary" onclick={forget}>Forget token on this device</button>
	</section>
{:else}
	<section aria-labelledby="owner">
		<h2 id="owner">Owner access</h2>
		{#if owner.rejected}
			<p class="notice" role="alert">
				The saved token was rejected (it may have been changed). Paste the current one.
			</p>
		{/if}
		<p>
			Paste the owner token once on each of your devices. It stays in this browser only and is
			sent only to the owner service. Visitors don't need this page.
		</p>
		<form onsubmit={save}>
			<label for="token">Owner token</label>
			<input
				id="token"
				type="password"
				autocomplete="off"
				autocapitalize="off"
				spellcheck="false"
				bind:value={input}
			/>
			<button type="submit" disabled={checking || !input.trim()}>
				{checking ? 'Checking…' : 'Save'}
			</button>
		</form>
	</section>
{/if}

<p class="status" class:error={isError} aria-live="polite">{message ?? ''}</p>

<style>
	nav a {
		display: inline-flex;
		align-items: center;
		min-height: 44px;
		color: var(--muted);
		text-decoration: none;
	}
	h1 {
		margin: 0.25rem 0 1rem;
		font-size: 1.6rem;
	}
	h2 {
		margin: 0 0 0.5rem;
		font-size: 1.1rem;
	}
	section {
		padding: 1rem;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: var(--radius);
	}
	form {
		display: flex;
		flex-wrap: wrap;
		gap: 0.6rem;
		align-items: end;
	}
	label {
		flex-basis: 100%;
		font-weight: 600;
	}
	input {
		flex: 1 1 16rem;
		min-height: 44px;
		padding: 0 0.75rem;
		border: 1px solid var(--border);
		border-radius: var(--radius);
		background: var(--bg);
		color: var(--text);
		font: inherit;
	}
	button {
		min-height: 44px;
		padding: 0 1.1rem;
		border: 0;
		border-radius: var(--radius);
		background: var(--accent);
		color: var(--accent-text);
		font-weight: 700;
		cursor: pointer;
	}
	button:disabled {
		opacity: 0.6;
		cursor: default;
	}
	button.secondary {
		background: transparent;
		color: var(--text);
		border: 1px solid var(--border);
	}
	.notice {
		padding: 0.6rem 0.8rem;
		border: 1px solid var(--accent);
		border-radius: var(--radius);
	}
	.status {
		min-height: 1.5em;
		margin-top: 1rem;
	}
	.status.error {
		color: var(--accent);
	}
</style>
