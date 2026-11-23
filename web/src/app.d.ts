// See https://svelte.dev/docs/kit/types#app.d.ts
declare global {
	namespace App {}
	/** The owner Worker's origin, from PUBLIC_WORKER_URL at build time ('' when unset). */
	const __WORKER_URL__: string;
}

export {};
