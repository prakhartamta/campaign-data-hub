// Mirrors backend/app/api/schemas.py. Money and ratios arrive as decimal strings, not numbers:
// pydantic serializes Decimal that way, which is what keeps a float off the money path entirely.
// Parse them only to compare; never to display.

export type Health = "pass" | "warn" | "fail";

export interface Figures {
  spend_usd: string;
  impressions: number;
  clicks: number;
  ctr: string | null;
  cpc: string | null;
}

export interface Totals extends Figures {
  rows: number;
}

export interface SummaryGroup extends Totals {
  key: string;
  platform: string;
}

export interface MetricFilters {
  platform: string | null;
  campaign: string | null;
  date_from: string | null;
  date_to: string | null;
}

export interface MetricsSummary {
  filters: MetricFilters;
  group_by: string;
  totals: Totals;
  groups: SummaryGroup[];
}

export interface Lineage {
  delivery_id: string;
  source_row: number;
  raw_spend: string;
  raw_spend_unit: string;
  raw_currency: string;
  fx_rate: string;
  raw_campaign: string | null;
  raw_date: string | null;
}

export interface MetricRow extends Figures {
  platform: string;
  campaign: string;
  date: string;
  lineage: Lineage;
}

export interface MetricsPage {
  filters: MetricFilters;
  total: number;
  limit: number;
  offset: number;
  rows: MetricRow[];
}

export interface Delivery {
  delivery_id: string;
  platform: string | null;
  week_start: string | null;
  week_end: string | null;
  is_missing: boolean;
  has_name_suffix: boolean;
  duplicate_of: string | null;
  health: Health;
  health_reason: string;
  rows_total: number;
  rows_accepted: number;
  rows_rejected: number;
  rows_suppressed: number;
  structural_error: string | null;
}

export interface Check {
  check_name: string;
  level: string;
  severity: string;
  status: string;
  rows_checked: number;
  rows_failed: number;
  message: string;
  samples: Record<string, unknown>[];
}

export interface RejectedRow {
  source_row: number;
  reasons: string[];
  raw: Record<string, unknown>;
  blamed: boolean;
}

export interface DeliveryDetail extends Delivery {
  content_hash: string | null;
  checks: Check[];
  rejected_rows: RejectedRow[];
}

export interface DeliveriesPage {
  total: number;
  deliveries: Delivery[];
}

export interface Run {
  run_id: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  deliveries_total: number;
  rows_accepted: number;
  rows_rejected: number;
  rows_suppressed: number;
  error: string | null;
}
