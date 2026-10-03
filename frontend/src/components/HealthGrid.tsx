import type { Delivery } from "../api/types";
import { platformLabel } from "../lib/labels";
import { buildGrid, slotKey } from "../lib/slots";
import { Legend } from "./Legend";
import { StatusIcon } from "./icons";

interface Props {
  deliveries: Delivery[];
  selected: { platform: string; weekStart: string } | null;
  onSelect: (platform: string, weekStart: string) => void;
}

export function HealthGrid({ deliveries, selected, onSelect }: Props) {
  const grid = buildGrid(deliveries);

  return (
    <div className="health">
      {/* The legend is part of the grid card: it is the key to what is directly below it. */}
      <Legend />

      <div className="health-grid head">
        <div className="col-head cap">platform</div>
        {grid.weeks.map((week) => (
          <div className="col-head" key={week}>
            {week}
          </div>
        ))}
      </div>

      {grid.platforms.map((platform) => (
        <div className="health-grid" key={platform}>
          {/* The label is for reading; `platform` stays the id used in the URL and the API. */}
          <div className="row-label">{platformLabel(platform)}</div>
          {grid.weeks.map((week) => {
            const slot = grid.slots.get(slotKey(platform, week));
            if (!slot) {
              // The schedule expects no file here at all, which is different from a file
              // that failed to arrive: that one is a delivery with is_missing set.
              return (
                <div key={week} className="cell-empty">
                  <span className="sr-only">no delivery expected</span>
                </div>
              );
            }
            const isSelected = selected?.platform === platform && selected?.weekStart === week;
            const missing = slot.deliveries.some((delivery) => delivery.is_missing);
            // Health is carried by the cell's word and icon as well as its colour. Colour alone
            // would hide the difference for a reviewer who cannot distinguish amber from green.
            const status = missing ? "missing" : slot.health;
            return (
              <button
                key={week}
                type="button"
                className="cell"
                onClick={() => onSelect(platform, week)}
                aria-pressed={isSelected}
                aria-label={`${platformLabel(platform)}, week of ${week}: ${status}`}
              >
                <span className={`chip ${status}`}>
                  <StatusIcon status={status} />
                  <span className="cap">{status}</span>
                  {slot.deliveries.length > 1 && (
                    <span className="chip-count">{slot.deliveries.length} files</span>
                  )}
                </span>
                {isSelected && <span className="cell-ring" />}
              </button>
            );
          })}
        </div>
      ))}

      <div className="health-foot" />

      {grid.unplaced.length > 0 && (
        <div className="unplaced">
          <h3 className="cap">unplaced files</h3>
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
