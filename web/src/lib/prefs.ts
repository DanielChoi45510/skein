// Per-browser view preferences (not read state; never synced).

import type { Order } from './group';
import { safeStorage, type Store } from './readState';

const ORDER_KEY = 'skein.threadOrder.v1';

export function loadThreadOrder(store: Store = safeStorage()): Order {
	try {
		return store.getItem(ORDER_KEY) === 'chronological' ? 'chronological' : 'newest';
	} catch {
		return 'newest';
	}
}

export function saveThreadOrder(order: Order, store: Store = safeStorage()): void {
	try {
		store.setItem(ORDER_KEY, order);
	} catch {
		// blocked storage: the choice just won't persist
	}
}
