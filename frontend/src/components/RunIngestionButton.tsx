import { useState } from "react";
import { ApiError, api } from "../api/client";
import type { Run } from "../api/types";
import { clockTime, count } from "../lib/format";

interface Props {
  /** Called once the run succeeds, so the page can refetch what the recompute replaced. */
  onDone: () => void;
}

interface Outcome {
  /** Counted in this tab. The API has no run sequence, only an opaque run_id. */
  number: number;
  run: Run;
}

// Re-ingestion is a full recompute, so everything on screen is stale the moment it returns. The
// page passes onDone to refetch rather than this button trying to patch state.
export function RunIngestionButton({ onDone }: Props) {
  const [running, setRunning] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [runs, setRuns] = useState(0);

  async function start() {
    setRunning(true);
    setError(null);
    try {
      const run = await api.ingest();
      const number = runs + 1;
      setRuns(number);
      setOutcome({ number, run });
      onDone();
    } catch (caught) {
      // A 409 is the expected answer when a run is already in flight, not a crash, so it is
      // shown in place with its message rather than thrown away.
      setError(
        caught instanceof ApiError ? caught : new ApiError(0, "unknown", String(caught), null),
      );
      setOutcome(null);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="ingest">
      <button type="button" onClick={start} disabled={running}>
        {running ? "Running…" : "Run ingestion"}
      </button>

      <span className="ingest-note" role="status" aria-live="polite">
        {error && (
          <span className="error">
            Ingestion failed — {error.message} ({error.code})
          </span>
        )}
        {!error && outcome && (
          <>
            Run #{outcome.number} finished at {clockTime(outcome.run.finished_at)}:{" "}
            {count(outcome.run.rows_accepted)} accepted, {count(outcome.run.rows_rejected)}{" "}
            rejected, {count(outcome.run.rows_suppressed)} suppressed
          </>
        )}
      </span>
    </div>
  );
}
