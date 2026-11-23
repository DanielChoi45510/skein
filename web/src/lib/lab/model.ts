// View models shared by the three lab directions: home tiles, the topic view
// and item metadata. Built on the real app's helpers so the lab shows the same
// feed the same way; only the presentation differs.

import { allItems, groupByLocalDay, type LocalDay } from '$lib/group';
import { kindLabel, leanLabel, paywallLabel } from '$lib/labels';
import { isNew, newSince, topicNewCount, type LastSeen } from '$lib/readState';
import { isThreaded, topicLayout, type Entry, type TopicLayout } from '$lib/topicView';
import type { ExportItem, FeedIndex, SourceSummary, ThreadSummary, TopicFeed } from '$lib/types';
import type { Spine } from './spine';
import type { LabState, Theme, View } from './state';

/** What every lab component needs besides its own data. */
export interface LabCtx {
	sources: Map<string, SourceSummary>;
	now: number;
	lastSeen: LastSeen;
	href: (patch: Partial<LabState>) => string; // a lab URL for another view
}

/** Props every direction's root component takes. */
export interface DirectionProps {
	view: View;
	theme: Theme;
	tiles: Tile[];
	generatedAt: string | null;
	topic: TopicView | null;
	spine: Spine | null;
	status: string | null; // loading or error text, shown instead of the view
	ctx: LabCtx;
}

export type Weight = 0 | 1 | 2 | 3; // 0: no sources; 3: the lead tile

export interface Tile {
	id: string;
	name: string;
	groupId: string;
	groupName: string;
	mode: string;
	active: boolean; // has sources
	newCount: number;
	shownCount: number; // shown items, thread items included
	threadCount: number;
	lead: Entry | null; // the topic's top thread or story
	weight: Weight;
	perDay: number[]; // items first seen per day, oldest first, ending at the export
}

const DAY = 86_400_000;

/** Shown items in a topic: single items within the cap plus listed threads' shown items. */
export function shownCount(feed: TopicFeed): number {
	return (
		allItems(feed.days).filter((i) => !i.collapsed).length +
		feed.threads.reduce((n, t) => n + t.item_count - t.collapsed_count, 0)
	);
}

/** Split off the lead: the newest live thread (a developing story beats a single), else the newest entry. */
export function splitLead(live: Entry[]): { lead: Entry | null; rest: Entry[] } {
	const lead = live.find((e) => e.kind === 'thread') ?? live[0] ?? null;
	return { lead, rest: live.filter((e) => e !== lead) };
}

/** The topic's top entry: its lead thread or story, else (flat) its most important item. */
export function leadEntry(feed: TopicFeed): Entry | null {
	if (isThreaded(feed)) return splitLead(topicLayout(feed).live).lead;
	const top = allItems(feed.days)
		.filter((i) => !i.collapsed)
		.sort((a, b) => b.importance - a.importance)[0];
	return top ? { kind: 'item', id: top.id, at: top.published_at, item: top } : null;
}

/** Items first seen per day over the last `days` days before `until`, oldest first. */
export function perDay(feed: TopicFeed, until: string, days = 7): number[] {
	const end = Date.parse(until);
	const buckets: number[] = Array(days).fill(0);
	const instants = [
		...allItems(feed.days).map((i) => i.first_seen_at),
		...feed.threads.flatMap((t) => t.first_seen)
	];
	for (const at of instants) {
		const ago = Math.floor((end - Date.parse(at)) / DAY);
		if (ago >= 0 && ago < days) buckets[days - 1 - ago]++;
	}
	return buckets;
}

export function buildTiles(
	index: FeedIndex,
	feeds: Record<string, TopicFeed | null>,
	lastSeen: LastSeen
): Tile[] {
	const tiles: Tile[] = index.groups.flatMap((g) =>
		g.topics.map((t) => {
			const feed = feeds[t.id] ?? null;
			return {
				id: t.id,
				name: t.name,
				groupId: g.id,
				groupName: g.name,
				mode: t.mode,
				active: t.has_sources,
				newCount: feed ? topicNewCount(feed, lastSeen[t.id]) : 0,
				shownCount: feed ? shownCount(feed) : 0,
				threadCount: feed?.threads.length ?? 0,
				lead: feed ? leadEntry(feed) : null,
				weight: 0 as Weight,
				perDay: feed ? perDay(feed, index.generated_at) : Array(7).fill(0)
			};
		})
	);
	// Busiest topic leads; the next two busy ones get wide tiles.
	const ranked = tiles
		.filter((t) => t.active)
		.sort((a, b) => b.shownCount - a.shownCount || b.newCount - a.newCount);
	ranked.forEach((t, i) => {
		t.weight = i === 0 && t.shownCount > 0 ? 3 : i <= 2 && t.shownCount > 1 ? 2 : 1;
	});
	return tiles;
}

/** Tiles grouped as in the index, idle topics last within each group. */
export function tilesByGroup(tiles: Tile[]): { id: string; name: string; tiles: Tile[] }[] {
	const groups = new Map<string, { id: string; name: string; tiles: Tile[] }>();
	for (const t of tiles) {
		const g = groups.get(t.groupId) ?? { id: t.groupId, name: t.groupName, tiles: [] };
		g.tiles.push(t);
		groups.set(t.groupId, g);
	}
	for (const g of groups.values()) g.tiles.sort((a, b) => Number(b.active) - Number(a.active));
	return [...groups.values()];
}

export interface TopicView {
	feed: TopicFeed;
	layout: TopicLayout | null; // threaded modes
	days: LocalDay[]; // flat modes
	empty: boolean;
}

export function topicView(feed: TopicFeed): TopicView {
	const layout = isThreaded(feed) ? topicLayout(feed) : null;
	const days = layout ? [] : groupByLocalDay(feed.days);
	const empty = layout
		? !layout.live.length && !layout.cooling.length && !layout.dormant.length
		: !days.length;
	return { feed, layout, days, empty };
}

/** The item an entry links out to: the story itself, or a thread's newest one. */
export const entryItem = (e: Entry): ExportItem => (e.kind === 'item' ? e.item : e.thread.latest);

export interface ItemMeta {
	source: string;
	kind: string | null;
	lean: string | null;
	paywall: string | null;
	trial: boolean;
	also: string[];
}

export function itemMeta(item: ExportItem, sources: Map<string, SourceSummary>): ItemMeta {
	const s = sources.get(item.source_id);
	return {
		source: s?.name ?? item.source_id,
		kind: kindLabel(s?.kind ?? null),
		lean: leanLabel(s?.lean ?? null),
		paywall: paywallLabel(s?.paywall),
		trial: s?.status === 'trial',
		also: item.also_covered_by.map((id) => sources.get(id)?.name ?? id)
	};
}

/** "New" badges need a previous visit to compare against (as in the real app). */
export const showNew = (item: ExportItem, since: string | undefined) =>
	since !== undefined && isNew(item, since);

export const threadNew = (t: ThreadSummary, since: string | undefined) =>
	since === undefined ? 0 : newSince(t.first_seen, since);

export function visitSummary(feed: TopicFeed, since: string | undefined): string {
	if (since === undefined) return 'First visit';
	const n = topicNewCount(feed, since);
	return n > 0 ? `${n} new since your last visit` : 'Nothing new since your last visit';
}

/** Compact age: "now", "12m", "5h", "3d". */
export function age(iso: string, now: number): string {
	const m = Math.max(0, Math.floor((now - Date.parse(iso)) / 60_000));
	if (m < 1) return 'now';
	if (m < 60) return `${m}m`;
	if (m < 1440) return `${Math.floor(m / 60)}h`;
	return `${Math.floor(m / 1440)}d`;
}

const clockFmt = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit' });
const dayFmt = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' });
const weekdayFmt = new Intl.DateTimeFormat('en-US', { weekday: 'short' });
const longFmt = new Intl.DateTimeFormat('en-US', {
	weekday: 'long',
	month: 'long',
	day: 'numeric',
	year: 'numeric'
});

export const clock = (iso: string) => clockFmt.format(new Date(iso));
export const shortDay = (iso: string) => dayFmt.format(new Date(iso));
export const weekday = (iso: string) => weekdayFmt.format(new Date(iso));
export const longDate = (iso: string) => longFmt.format(new Date(iso));
