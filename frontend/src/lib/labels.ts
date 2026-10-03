// Display names for the things the backend names by id.
//
// Ids are what the URL, the API and the database use. These strings exist only to be read, so
// nothing here may ever be sent back to the server.

const PLATFORMS: Record<string, string> = {
  google_ads: "Google Ads",
  meta_ads: "Meta Ads",
  linkedin_ads: "LinkedIn Ads",
};

/** An unmapped platform falls back to its id, so a new one appears rather than disappearing. */
export function platformLabel(id: string | null): string {
  if (id === null) return "unknown platform";
  return PLATFORMS[id] ?? id;
}

const LEVELS: Record<string, string> = {
  row: "row",
  file: "file",
  delivery: "delivery",
};

/** Narrow to broad, which is the order the pipeline runs them in. */
const LEVEL_ORDER: Record<string, number> = { row: 0, file: 1, delivery: 2 };

export function levelLabel(level: string): string {
  return LEVELS[level] ?? level;
}

export function levelRank(level: string): number {
  return LEVEL_ORDER[level] ?? 99;
}

/** A check name as prose: row_fields_readable -> "row fields readable". */
export function checkLabel(name: string): string {
  return name.replace(/_/g, " ");
}
