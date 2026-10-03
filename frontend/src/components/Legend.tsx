// What the grid's colours mean. Each entry repeats the glyph the cell uses, so the legend holds
// for a reader who cannot tell amber from green.

const ENTRIES: { health: string; glyph: string; label: string; meaning: string }[] = [
  { health: "pass", glyph: "●", label: "pass", meaning: "nothing to report" },
  { health: "warn", glyph: "▲", label: "warn", meaning: "usable, with something noted" },
  { health: "fail", glyph: "✕", label: "fail", meaning: "do not trust without reading why" },
  { health: "fail", glyph: "✕", label: "missing", meaning: "no file arrived for the slot" },
];

export function Legend() {
  return (
    <ul className="legend">
      {ENTRIES.map((entry) => (
        <li key={entry.label}>
          <span className={`tag ${entry.health}`}>
            <span aria-hidden="true">{entry.glyph}</span> {entry.label}
          </span>
          <span className="muted">{entry.meaning}</span>
        </li>
      ))}
    </ul>
  );
}
