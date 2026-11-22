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
