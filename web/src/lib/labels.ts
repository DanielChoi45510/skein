const KIND: Record<string, string> = {
	reporting: 'Reporting',
	analysis: 'Analysis',
	opinion: 'Opinion',
	study: 'Study',
	listing: 'Listing',
	guide: 'Guide'
};

const LEAN: Record<string, string> = {
	left: 'Left',
	'center-left': 'Center-left',
	center: 'Center',
	'center-right': 'Center-right',
	right: 'Right'
};

export const kindLabel = (kind: string | null) => (kind ? (KIND[kind] ?? kind) : null);
export const leanLabel = (lean: string | null) => (lean ? (LEAN[lean] ?? lean) : null);
