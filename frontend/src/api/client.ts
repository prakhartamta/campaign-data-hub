// The one place that talks to the backend. Every failure arrives as the API's error envelope,
// so the UI has one error type to render rather than three.

import type {
  DeliveriesPage,
  DeliveryDetail,
  MetricsPage,
  MetricsSummary,
  Run,
} from "./types";

const BASE = "/api/v1";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(BASE + path, init);
  } catch {
    // The backend is not answering at all. Named separately because "failed to fetch" in a
    // console is the one error whose fix is "start the server", not "look at the code".
    throw new ApiError(0, "unreachable", "cannot reach the API at " + BASE, null);
  }

  const text = await response.text();
  const body = text ? (JSON.parse(text) as unknown) : null;

  if (!response.ok) {
    const envelope = (body as { error?: { code: string; message: string; details: unknown } })
      ?.error;
    throw new ApiError(
      response.status,
      envelope?.code ?? "unknown",
      envelope?.message ?? response.statusText,
      envelope?.details ?? null,
    );
  }
  return body as T;
}

export const api = {
  summary: (query: string) => request<MetricsSummary>(`/metrics/summary?${query}`),
  metrics: (query: string) => request<MetricsPage>(`/metrics?${query}`),
  deliveries: () => request<DeliveriesPage>("/deliveries"),
  // Encoded because a delivery id is a file name and carries a dot and an extension.
  delivery: (id: string) => request<DeliveryDetail>(`/deliveries/${encodeURIComponent(id)}`),
  ingest: () => request<Run>("/ingestions", { method: "POST" }),
};
