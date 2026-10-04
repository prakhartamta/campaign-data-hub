import { useState } from "react";
import { ApiError, api } from "../api/client";
import type { Run } from "../api/types";
import { clockTime, count } from "../lib/format";
import { Spinner } from "./icons";

interface Props {
  /** Called once the run succeeds, so the page can refetch what the recompute replaced. */
  onDone: () => void;
  /** Called when a run starts and when it ends, so the page can show loading on its data. */
  onRunningChange: (running: boolean) => void;
}

/**
 * The shortest time the running state stays on screen.
 *
 * A run finishes in under 100ms, too fast to see, so a click looks like it did nothing. The
 * timer runs alongside the request, so it only ever pads a fast run and never slows a slow one.
 */
const MIN_RUNNING_MS = 1000;

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

interface Outcome {
  /** Counted in this tab. The API has no run sequence, only an opaque run_id. */
  number: number;
  run: Run;
}

// Re-ingestion is a full recompute, so everything on screen is stale the moment it returns. The
// page passes onDone to refetch rather than this button trying to patch state.
export function RunIngestionButton({ onDone, onRunningChange }: Props) {
  const [running, setRunning] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [runs, setRuns] = useState(0);

  async function start() {
    setRunning(true);
    onRunningChange(true);
    setError(null);
    try {
      // Both start now; this resolves when the slower of the two does. An error still shows at
      // once, because Promise.all rejects as soon as the request does.
      const [run] = await Promise.all([api.ingest(), wait(MIN_RUNNING_MS)]);
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
      onRunningChange(false);
    }
  }

  return (
    <div className="ingest">
      {/* The outcome reads left of the button, where the eye already is after clicking it. */}
      <span className="ingest-note" role="status" aria-live="polite">
        {running && "Running ingestion…"}
        {!running && error && (
          <span className="error">
            Ingestion failed — {error.message} ({error.code})
          </span>
        )}
        {!running && !error && outcome && (
          <>
            <span className="run-number">Run #{outcome.number}</span> finished at{" "}
            {clockTime(outcome.run.finished_at)}: {count(outcome.run.rows_accepted)} accepted,{" "}
            {count(outcome.run.rows_rejected)} rejected, {count(outcome.run.rows_suppressed)}{" "}
            suppressed
          </>
        )}
      </span>

      <button
        type="button"
        className="btn-primary"
        onClick={start}
        disabled={running}
        aria-busy={running || undefined}
      >
        {running ? (
          <>
            <Spinner />
            Running…
          </>
        ) : (
          "Run ingestion"
        )}
      </button>
    </div>
  );
}
