import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

// GitHub Pages serves a project site under /<repo>; the workflow sets BASE_PATH=/<repo>.
const base = process.env.BASE_PATH ?? '';
if (base && (!base.startsWith('/') || base.endsWith('/'))) {
	throw new Error(`BASE_PATH must look like "/skein", got "${base}"`);
}

/** @type {import('@sveltejs/kit').Config} */
export default {
	preprocess: vitePreprocess(),
	kit: {
		adapter: adapter({ strict: true }),
		paths: { base }
	}
};
