// The health grid is a grid of slots, not of deliveries.
//
// A slot is one (platform, week) the schedule expects a file for. Most hold one delivery; the
// Google 06-15 slot holds two, the original and its resend. Drawing a cell per delivery would
// put a seventeenth box in a six-column grid with no column of its own.

import type { Delivery, Health } from "../api/types";

export interface Slot {
  platform: string;
  weekStart: string;
  deliveries: Delivery[];
  health: Health;
}

export interface Grid {
  platforms: string[];
  weeks: string[];
  slots: Map<string, Slot>;
  /** Files that matched no platform or no week, so they have no cell to sit in. */
  unplaced: Delivery[];
}

const RANK: Record<Health, number> = { pass: 0, warn: 1, fail: 2 };

export function slotKey(platform: string, weekStart: string): string {
  return `${platform}|${weekStart}`;
}

/**
 * The colour of a cell holding more than one delivery.
 *
 * The worse of the two, because a slot holding a clean file and a failed one is not a clean
 * slot, and the failure is the thing a reviewer must not miss.
 */
export function worstHealth(deliveries: Delivery[]): Health {
  let worst: Health = "pass";
  for (const delivery of deliveries) {
    if (RANK[delivery.health] > RANK[worst]) worst = delivery.health;
  }
  return worst;
}

export function buildGrid(deliveries: Delivery[]): Grid {
  const platforms = new Set<string>();
  const weeks = new Set<string>();
  const slots = new Map<string, Slot>();
  const unplaced: Delivery[] = [];

  for (const delivery of deliveries) {
    if (delivery.platform === null || delivery.week_start === null) {
      unplaced.push(delivery);
      continue;
    }
    platforms.add(delivery.platform);
    weeks.add(delivery.week_start);

    const key = slotKey(delivery.platform, delivery.week_start);
    const existing = slots.get(key);
    if (existing) {
      existing.deliveries.push(delivery);
      existing.health = worstHealth(existing.deliveries);
    } else {
      slots.set(key, {
        platform: delivery.platform,
        weekStart: delivery.week_start,
        deliveries: [delivery],
        health: delivery.health,
      });
    }
  }

  return {
    platforms: [...platforms].sort(),
    weeks: [...weeks].sort(),
    slots,
    unplaced,
  };
}
