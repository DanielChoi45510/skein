// Dates and local days. The export groups by UTC day; the UI regroups by the
// viewer's local day (DESIGN §6.8). `timeZone` is a parameter for testability.

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** YYYY-MM-DD of an instant in the given (default: the viewer's) time zone. */
export function localDayKey(instant: string | number | Date, timeZone?: string): string {
	// en-CA formats dates as YYYY-MM-DD.
	return new Intl.DateTimeFormat('en-CA', {
		timeZone,
		year: 'numeric',
		month: '2-digit',
		day: '2-digit'
	}).format(new Date(instant));
}

/** "Today", "Yesterday", or e.g. "Wednesday, Nov 19". */
export function dayLabel(key: string, now: number = Date.now(), timeZone?: string): string {
	if (key === localDayKey(now, timeZone)) return 'Today';
	if (key === localDayKey(now - DAY, timeZone)) return 'Yesterday';
	// Noon UTC on that date is the same calendar day in every zone within ±11 h.
	return new Intl.DateTimeFormat('en-US', {
		weekday: 'long',
		month: 'short',
		day: 'numeric',
		timeZone: 'UTC'
	}).format(new Date(`${key}T12:00:00Z`));
}

const relative = new Intl.RelativeTimeFormat('en', { numeric: 'auto', style: 'long' });

/** "just now", "5 minutes ago", "3 hours ago", "yesterday", "4 days ago". */
export function relativeTime(iso: string, now: number = Date.now()): string {
	const diff = Math.max(0, now - Date.parse(iso));
	if (diff < MINUTE) return 'just now';
	if (diff < HOUR) return relative.format(-Math.floor(diff / MINUTE), 'minute');
	if (diff < DAY) return relative.format(-Math.floor(diff / HOUR), 'hour');
	return relative.format(-Math.floor(diff / DAY), 'day');
}

/** Full local date and time, for tooltips. */
export function fullDate(iso: string, timeZone?: string): string {
	return new Intl.DateTimeFormat('en-US', {
		dateStyle: 'full',
		timeStyle: 'short',
		timeZone
	}).format(new Date(iso));
}
