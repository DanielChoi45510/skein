// Mirror of pipeline/export/models.py (schema_version 2). Keep the two in sync.

export const SCHEMA_VERSION = 2;

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

export type ThreadState = 'active' | 'cooling' | 'dormant';

/** A thread as listed in its topic: promoted (not pending), not archived. */
export interface ThreadSummary {
	id: string;
	title: string;
	kind: string; // story | question | tracker | fixed
	state: ThreadState;
	last_item_at: string; // newest item's published_at
	item_count: number; // collapsed included
	collapsed_count: number;
	latest_first_seen_at: string;
	first_seen: string[]; // first_seen_at of every shown item, newest first
	latest: ExportItem; // newest item, for a preview line
}

export interface TopicFeed {
	schema_version: number;
	id: string;
	name: string;
	group: string;
	mode: string;
	threads: ThreadSummary[]; // newest update first; empty for unthreaded modes
	days: Day[]; // in threaded modes only items not in a listed thread
}

export interface ThreadFeed {
	schema_version: number;
	id: string;
	topic_id: string;
	title: string;
	kind: string;
	state: ThreadState;
	created_at: string;
	last_item_at: string;
	days: Day[]; // per-thread daily cap
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
