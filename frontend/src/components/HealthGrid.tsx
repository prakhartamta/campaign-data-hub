import type { Delivery } from "../api/types";
import { platformLabel } from "../lib/labels";
import { buildGrid, slotKey } from "../lib/slots";

interface Props {
  deliveries: Delivery[];
  selected: { platform: string; weekStart: string } | null;
  onSelect: (platform: string, weekStart: string) => void;
}

// Health is carried by the cell's label as well as its colour. Colour alone would hide the
// difference for a reviewer who cannot distinguish amber from green.
const GLYPH: Record<string, string> = { pass: "●", warn: "▲", fail: "✕" };

export function HealthGrid({ deliveries, selected, onSelect }: Props) {
  const grid = buildGrid(deliveries);

  return (
    <div className="health">
      <table className="grid-table health-grid">
        <thead>
          <tr>
            <th>platform</th>
            {grid.weeks.map((week) => (
              <th key={week}>{week}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grid.platforms.map((platform) => (
            <tr key={platform}>
              {/* The label is for reading; `platform` stays the id used in the URL and the API. */}
              <th scope="row">{platformLabel(platform)}</th>
              {grid.weeks.map((week) => {
                const slot = grid.slots.get(slotKey(platform, week));
                if (!slot) {
                  // The schedule expects no file here at all, which is different from a file
                  // that failed to arrive: that one is a delivery with is_missing set.
                  return (
                    <td key={week} className="cell none">
                      <span className="sr-only">no delivery expected</span>
                    </td>
                  );
                }
                const isSelected =
                  selected?.platform === platform && selected?.weekStart === week;
                const missing = slot.deliveries.some((delivery) => delivery.is_missing);
                return (
                  <td key={week} className="cell">
                    <button
                      type="button"
                      className={`chip ${slot.health}${isSelected ? " selected" : ""}`}
                      onClick={() => onSelect(platform, week)}
                      aria-pressed={isSelected}
                    >
                      <span aria-hidden="true">{GLYPH[slot.health]}</span>
                      <span>{missing ? "missing" : slot.health}</span>
                      {slot.deliveries.length > 1 && (
                        <span className="chip-count">{slot.deliveries.length} files</span>
                      )}
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>

      {grid.unplaced.length > 0 && (
        <div className="unplaced">
          <h3>unplaced files</h3>
          <ul>
            {grid.unplaced.map((delivery) => (
              <li key={delivery.delivery_id}>
                {delivery.delivery_id} {delivery.structural_error ?? ""}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
