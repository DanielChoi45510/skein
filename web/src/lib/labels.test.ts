import { describe, expect, it } from 'vitest';
import { kindLabel, leanLabel, paywallLabel } from './labels';

describe('labels', () => {
	it('maps the AllSides lean scale', () => {
		expect(leanLabel('lean_left')).toBe('Lean left');
		expect(leanLabel('lean_right')).toBe('Lean right');
		expect(leanLabel('center')).toBe('Center');
		expect(leanLabel(null)).toBeNull();
	});
	it('shows a lock only for partial or full paywalls', () => {
		expect(paywallLabel('full')).toBe('Subscription required');
		expect(paywallLabel('partial')).toBe('Partly paywalled');
		expect(paywallLabel('none')).toBeNull();
		expect(paywallLabel(undefined)).toBeNull(); // older feeds
	});
	it('labels kinds', () => {
		expect(kindLabel('opinion')).toBe('Opinion');
		expect(kindLabel(null)).toBeNull();
	});
});
