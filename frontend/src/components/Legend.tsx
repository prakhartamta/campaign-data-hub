// What the grid's colours mean. Each entry repeats the icon the cell uses, so the legend holds
// for a reader who cannot tell amber from green.

import { StatusIcon } from "./icons";

const ENTRIES: { status: string; label: string; meaning: string }[] = [
  { status: "pass", label: "pass", meaning: "nothing to report" },
  { status: "warn", label: "warn", meaning: "usable, with something noted" },
  { status: "fail", label: "fail", meaning: "do not trust without reading why" },
  { status: "missing", label: "missing", meaning: "no file arrived for the slot" },
];

export function Legend() {
  return (
    <ul className="legend">
      {ENTRIES.map((entry) => (
        <li key={entry.label} className={entry.status}>
          <StatusIcon status={entry.status} size={14} />
          <span>
            <span className="legend-status cap">{entry.label}</span> &mdash; {entry.meaning}
          </span>
        </li>
      ))}
    </ul>
  );
}
