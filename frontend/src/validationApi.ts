import type {
  TrackingReport,
  ValidationDataset,
  ValidationOptions,
  ValidationReport,
} from "./validationTypes";

async function fetchResult(path: string, options?: RequestInit) {
  const response = await fetch(`/api${path}`, options);
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail))
        message = body.detail
          .map(
            (issue: { loc?: (string | number)[]; msg?: string }) =>
              `${issue.loc?.slice(1).join(".") || "Input"}: ${issue.msg || "Invalid value"}`,
          )
          .join("; ");
    } catch {
      /* The local proxy may return plain text. */
    }
    throw new Error(message);
  }
  return response;
}
function post(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}
export const validationApi = {
  example: async (): Promise<ValidationDataset> =>
    (await fetchResult("/validation/example")).json(),
  import: async (file: File): Promise<ValidationDataset> => {
    const body = new FormData();
    body.append("file", file);
    return (
      await fetchResult("/validation/import", { method: "POST", body })
    ).json();
  },
  evaluate: async (
    dataset: ValidationDataset,
    options: ValidationOptions,
  ): Promise<ValidationReport> =>
    (
      await fetchResult("/validation/evaluate", post({ dataset, options }))
    ).json(),
  export: async (
    dataset: ValidationDataset,
    options: ValidationOptions,
    format: "csv" | "json",
  ): Promise<Blob> =>
    (
      await fetchResult(
        `/validation/export?format=${format}`,
        post({ dataset, options }),
      )
    ).blob(),
  benchmark: async (): Promise<TrackingReport> =>
    (await fetchResult("/benchmarks/tracking", { method: "POST" })).json(),
  exportBenchmark: async (
    report: TrackingReport,
    format: "csv" | "json",
  ): Promise<Blob> =>
    (
      await fetchResult(
        `/benchmarks/tracking/export?format=${format}`,
        post(report),
      )
    ).blob(),
};

export function downloadResult(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
