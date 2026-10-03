import type { Delivery } from "../api/types";

export interface FilterValues {
  platform: string;
  dateFrom: string;
  dateTo: string;
}

interface Props {
  values: FilterValues;
  platforms: string[];
  onChange: (next: Partial<FilterValues>) => void;
  onClear: () => void;
}

// The platform list comes from the deliveries the API reported rather than a hardcoded array,
// so adding a platform to the pipeline adds it to this dropdown with no frontend change.
export function platformsFrom(deliveries: Delivery[]): string[] {
  const found = new Set<string>();
  for (const delivery of deliveries) {
    if (delivery.platform !== null) found.add(delivery.platform);
  }
  return [...found].sort();
}

export function Filters({ values, platforms, onChange, onClear }: Props) {
  const active = values.platform !== "" || values.dateFrom !== "" || values.dateTo !== "";

  return (
    <div className="filters">
      <label>
        platform
        <select
          value={values.platform}
          onChange={(event) => onChange({ platform: event.target.value })}
        >
          <option value="">all</option>
          {platforms.map((platform) => (
            <option key={platform} value={platform}>
              {platform}
            </option>
          ))}
        </select>
      </label>

      <label>
        from
        <input
          type="date"
          value={values.dateFrom}
          onChange={(event) => onChange({ dateFrom: event.target.value })}
        />
      </label>

      <label>
        to
        <input
          type="date"
          value={values.dateTo}
          onChange={(event) => onChange({ dateTo: event.target.value })}
        />
      </label>

      <button type="button" onClick={onClear} disabled={!active}>
        clear
      </button>
    </div>
  );
}
