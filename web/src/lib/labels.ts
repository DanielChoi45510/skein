const KIND: Record<string, string> = {
	reporting: 'Reporting',
	analysis: 'Analysis',
	opinion: 'Opinion',
	study: 'Study',
	listing: 'Listing',
	guide: 'Guide'
};

// AllSides scale (config/sources.yaml `lean`).
const LEAN: Record<string, string> = {
	left: 'Left',
	lean_left: 'Lean left',
	center: 'Center',
	lean_right: 'Lean right',
	right: 'Right'
};

export const kindLabel = (kind: string | null) => (kind ? (KIND[kind] ?? kind) : null);
export const leanLabel = (lean: string | null) => (lean ? (LEAN[lean] ?? lean) : null);

/** Lock badge text for paywalled sources (DESIGN §9.1), or null. */
export function paywallLabel(paywall: string | undefined): string | null {
	if (paywall === 'full') return 'Subscription required';
	if (paywall === 'partial') return 'Partly paywalled';
	return null;
}

/** Up to two initials for a source's image fallback: "Example Times > World" → "ET". */
export function sourceInitials(name: string): string {
	const words = name.split(/[^\p{L}\p{N}]+/u).filter(Boolean);
	const letters = words.length > 1 ? words[0][0] + words[1][0] : (words[0] ?? '?').slice(0, 2);
	return letters.toUpperCase();
}
