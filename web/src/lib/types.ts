// Mirror of pipeline/export/models.py (schema_version 1). Keep the two in sync.

export const SCHEMA_VERSION = 1;

export interface ExportItem {
	id: string;
	title: string;
	url: string;
	source_id: string;
	published_at: string; // ISO 8601, UTC
	first_seen_at: string;
	excerpt: string | null;
	importance: number;
	also_covered_by: string[];
	collapsed: boolean; // over the cap: behind "+N more"
}

export interface Day {
	date: string; // UTC day, YYYY-MM-DD
	items: ExportItem[];
}

export interface TopicFeed {
	schema_version: number;
	id: string;
	name: string;
	group: string;
	mode: string;
	days: Day[];
}

export interface TopicSummary {
	id: string;
	name: string;
	mode: string;
	has_sources: boolean;
	visible_count: number;
	collapsed_count: number;
	latest_first_seen_at: string | null;
}

export interface GroupSummary {
	id: string;
	name: string;
	topics: TopicSummary[];
}

export interface SourceSummary {
	id: string;
	name: string;
	type: string;
	status: string;
	lean: string | null;
	kind: string | null;
	paywall?: 'none' | 'partial' | 'full'; // absent in feeds exported before sources-v2
}

export interface FeedIndex {
	schema_version: number;
	generated_at: string;
	groups: GroupSummary[];
	sources: SourceSummary[];
}
