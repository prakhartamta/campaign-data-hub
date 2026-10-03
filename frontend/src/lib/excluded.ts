// Reading the original values off an excluded row.
//
// `raw` arrives in one of three shapes, because it is whatever the row looked like before it was
// excluded. A row dropped after parsing carries the canonical field names; a row the adapter
// could never parse carries that platform's own column names, which differ per platform:
//
//   canonical          campaign, date, spend, spend_unit, currency, impressions, clicks
//   Meta CSV           campaign_name, date, spend_usd, impressions, clicks
//   LinkedIn JSON      campaign, date_ts, spend.amount, spend.currency, impressions
//
// So each field is read through a list of candidate keys rather than one.

import type { RejectedRow } from "../api/types";

export interface OriginalValues {
  campaign: string;
  date: string;
  spend: string;
  impressions: string;
  clicks: string;
}

const ABSENT = "—";

function read(raw: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = raw[key];
    if (value === undefined || value === null) continue;
    const text = String(value).trim();
    // An empty string is how a missing CSV cell arrives, so it counts as absent, not as a value.
    if (text !== "") return text;
  }
  return null;
}

/** Epoch milliseconds, which is LinkedIn's only date format, rendered as the day it means. */
function fromEpochMillis(value: string): string | null {
  const millis = Number(value);
  if (!Number.isFinite(millis)) return null;
  const parsed = new Date(millis);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString().slice(0, 10);
}

export function originalValues(row: RejectedRow): OriginalValues {
  const raw = row.raw;

  const date = read(raw, ["date"]);
  const epoch = read(raw, ["date_ts"]);

  const amount = read(raw, ["spend", "spend_usd", "spend.amount"]);
  // The unit is explicit on a canonical row, implied by the column name on a Meta row, and the
  // currency itself on a LinkedIn one.
  let unit = read(raw, ["spend_unit", "spend.currency", "currency"]);
  if (unit === null && raw["spend_usd"] !== undefined) unit = "usd";

  return {
    campaign: read(raw, ["campaign", "campaign_name"]) ?? ABSENT,
    date: date ?? (epoch !== null ? fromEpochMillis(epoch) ?? epoch : ABSENT),
    spend: amount === null ? ABSENT : unit === null ? amount : `${amount} ${unit}`,
    impressions: read(raw, ["impressions"]) ?? ABSENT,
    clicks: read(raw, ["clicks"]) ?? ABSENT,
  };
}

/**
 * Why the row is not in the metrics.
 *
 * "rejected" means it failed a validity check and is counted against the delivery; "suppressed"
 * means the row itself was fine but was removed as a duplicate or with a quarantined file.
 */
export function exclusionType(row: RejectedRow): "rejected" | "suppressed" {
  return row.blamed ? "rejected" : "suppressed";
}
