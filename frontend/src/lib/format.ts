// Display helpers. Money is grouped by string surgery, never by Number(), so the decimal the
// API computed is the decimal shown. Parsing is reserved for sorting, where only order matters.

const EM_DASH = "—";

export function money(value: string): string {
  const negative = value.startsWith("-");
  const unsigned = negative ? value.slice(1) : value;
  const [whole = "0", cents = "00"] = unsigned.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${negative ? "-" : ""}$${grouped}.${cents}`;
}

export function count(value: number): string {
  return value.toLocaleString("en-US");
}

/** CTR as a percentage. Null means the denominator was zero, which is not the same as 0%. */
export function percent(value: string | null): string {
  if (value === null) return EM_DASH;
  return `${(Number(value) * 100).toFixed(2)}%`;
}

/** CPC. Four decimals, because it is a per-click rate and cents would round most of it away. */
export function rate(value: string | null): string {
  if (value === null) return EM_DASH;
  return `$${value}`;
}

export function date(value: string | null): string {
  return value ?? "unknown";
}

/** For sorting only. Null sorts below every real value. */
export function sortable(value: string | null): number {
  return value === null ? Number.NEGATIVE_INFINITY : Number(value);
}

/**
 * A wall-clock time from an API timestamp.
 *
 * The pipeline records UTC but SQLite drops the offset, so the string arrives with no zone and
 * JS would read it as local time. Appending Z when no offset is present keeps the displayed
 * time honest.
 */
export function clockTime(iso: string | null): string {
  if (iso === null) return EM_DASH;
  const stamped = /(Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`;
  const parsed = new Date(stamped);
  return Number.isNaN(parsed.getTime()) ? iso : parsed.toLocaleTimeString();
}
