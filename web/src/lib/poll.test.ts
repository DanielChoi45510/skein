import { describe, expect, it } from 'vitest';
import { poll } from './poll';

function fakeEnv() {
	const env = {
		time: 0,
		visible: true,
		intervals: [] as (() => void)[],
		listeners: [] as (() => void)[],
		cleared: false,
		now: () => env.time,
		isVisible: () => env.visible,
		setInterval: (fn: () => void) => {
			env.intervals.push(fn);
			return 1;
		},
		clearInterval: () => {
			env.cleared = true;
		},
		onVisibilityChange: (fn: () => void) => {
			env.listeners.push(fn);
			return () => {
				env.listeners = env.listeners.filter((l) => l !== fn);
			};
		},
		tick: () => env.intervals.forEach((f) => f()),
		show: () => {
			env.visible = true;
			env.listeners.forEach((f) => f());
		}
	};
	return env;
}

describe('poll', () => {
	it('refreshes only after the interval, and only while visible', () => {
		const env = fakeEnv();
		let calls = 0;
		poll(() => calls++, 1000, env);
		env.time = 500;
		env.tick();
		expect(calls).toBe(0);
		env.time = 1000;
		env.tick();
		expect(calls).toBe(1);
		env.visible = false;
		env.time = 5000;
		env.tick();
		expect(calls).toBe(1);
	});

	it('refreshes when a stale tab becomes visible', () => {
		const env = fakeEnv();
		let calls = 0;
		poll(() => calls++, 1000, env);
		env.visible = false;
		env.time = 3000;
		env.show();
		expect(calls).toBe(1);
	});

	it('stops cleanly', () => {
		const env = fakeEnv();
		const stop = poll(() => {}, 1000, env);
		stop();
		expect(env.cleared).toBe(true);
		expect(env.listeners).toEqual([]);
	});
});
