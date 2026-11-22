import { describe, expect, it } from 'vitest';
import { dayLabel, localDayKey, relativeTime } from './time';

const NOW = Date.parse('2026-11-21T18:00:00Z');

describe('localDayKey', () => {
	it('uses the given time zone', () => {
		// 01:30 UTC on the 22nd is still the 21st in New York
		expect(localDayKey('2026-11-22T01:30:00Z', 'America/New_York')).toBe('2026-11-21');
		expect(localDayKey('2026-11-22T01:30:00Z', 'UTC')).toBe('2026-11-22');
		expect(localDayKey('2026-11-21T20:00:00Z', 'Asia/Tokyo')).toBe('2026-11-22');
	});
});

describe('dayLabel', () => {
	it('names today and yesterday in the viewer zone', () => {
		expect(dayLabel('2026-11-21', NOW, 'America/New_York')).toBe('Today');
		expect(dayLabel('2026-11-20', NOW, 'America/New_York')).toBe('Yesterday');
	});
	it('formats older days with weekday and date', () => {
		expect(dayLabel('2026-11-18', NOW, 'America/New_York')).toBe('Wednesday, Nov 18');
	});
	it('handles Today across the UTC boundary', () => {
		const lateEvening = Date.parse('2026-11-22T03:00:00Z'); // 22:00 on the 21st in NY
		expect(dayLabel('2026-11-21', lateEvening, 'America/New_York')).toBe('Today');
	});
});

describe('relativeTime', () => {
	it.each([
		['2026-11-21T17:59:30Z', 'just now'],
		['2026-11-21T17:55:00Z', '5 minutes ago'],
		['2026-11-21T15:00:00Z', '3 hours ago'],
		['2026-11-20T17:00:00Z', 'yesterday'],
		['2026-11-17T18:00:00Z', '4 days ago'],
		['2026-11-21T19:00:00Z', 'just now'] // future (clock skew) never says "in ..."
	])('%s → %s', (iso, expected) => {
		expect(relativeTime(iso, NOW)).toBe(expected);
	});
	it('handles fractional-second timestamps', () => {
		expect(relativeTime('2026-11-21T15:00:00.123456Z', NOW)).toBe('2 hours ago');
	});
});
