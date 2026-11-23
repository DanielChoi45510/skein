import type { Day, ExportItem } from './types';
import { localDayKey } from './time';

export interface LocalDay {
	key: string; // local YYYY-MM-DD
	shown: ExportItem[]; // within the cap, by importance
	more: ExportItem[]; // collapsed ("+N more"), by importance
}

const byImportance = (a: ExportItem, b: ExportItem) =>
	b.importance - a.importance || Date.parse(b.published_at) - Date.parse(a.published_at);

/** Regroup the export's UTC days into the viewer's local days, newest first. */
export function groupByLocalDay(days: Day[], timeZone?: string): LocalDay[] {
	const groups = new Map<string, ExportItem[]>();
	for (const day of days) {
		for (const item of day.items) {
			const key = localDayKey(item.published_at, timeZone);
			const list = groups.get(key);
			if (list) list.push(item);
			else groups.set(key, [item]);
		}
	}
	return [...groups.entries()]
		.sort(([a], [b]) => (a < b ? 1 : a > b ? -1 : 0))
		.map(([key, items]) => ({
			key,
			shown: items.filter((i) => !i.collapsed).sort(byImportance),
			more: items.filter((i) => i.collapsed).sort(byImportance)
		}));
}

export function allItems(days: Day[]): ExportItem[] {
	return days.flatMap((d) => d.items);
}

export type Order = 'newest' | 'chronological';

/**
 * A thread's local days in time order (the catch-up view): newest first, or
 * oldest first to read the story as it unfolded. Which items are shown and
 * which sit behind "+N more" doesn't change: the export's cap decides that.
 */
export function inTimeOrder(days: LocalDay[], order: Order): LocalDay[] {
	const sign = order === 'newest' ? -1 : 1;
	const byTime = (a: ExportItem, b: ExportItem) =>
		sign * (Date.parse(a.published_at) - Date.parse(b.published_at)) ||
		(a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
	const ordered = days.map((d) => ({
		key: d.key,
		shown: [...d.shown].sort(byTime),
		more: [...d.more].sort(byTime)
	}));
	return order === 'newest' ? ordered : ordered.reverse();
}
