import type {
  EventMatch,
  FieldEligibility,
  FieldEvaluation,
  FieldEvaluationRequest,
  FieldSession,
  FieldSessionInput,
  FieldSourceOption,
  SyncConfig,
} from "./fieldTypes";

async function result(path: string, options?: RequestInit) {
  const response = await fetch(`/api${path}`, options);
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail))
        message = body.detail
          .map(
            (item: { loc?: (string | number)[]; msg?: string }) =>
              `${item.loc?.slice(1).join(".") || "Input"}: ${item.msg || "Invalid value"}`,
          )
          .join("; ");
    } catch {
      /* Proxy failures can be plain text. */
    }
    throw new Error(message);
  }
  return response;
}
const json = (method: string, value: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(value),
});
const fileBody = (file: File) => {
  const body = new FormData();
  body.append("file", file);
  return { method: "POST", body };
};
const sessionPath = (id: string) => `/field-sessions/${encodeURIComponent(id)}`;
export const fieldApi = {
  sources: async (): Promise<{ sources: FieldSourceOption[] }> =>
    (await result("/field-sources")).json(),
  list: async (): Promise<{ sessions: FieldSession[] }> =>
    (await result("/field-sessions")).json(),
  get: async (id: string): Promise<FieldSession> =>
    (await result(sessionPath(id))).json(),
  create: async (value: FieldSessionInput): Promise<FieldSession> =>
    (await result("/field-sessions", json("POST", value))).json(),
  update: async (id: string, value: FieldSessionInput): Promise<FieldSession> =>
    (await result(sessionPath(id), json("PUT", value))).json(),
  delete: async (id: string): Promise<void> => {
    await result(sessionPath(id), { method: "DELETE" });
  },
  fromObservation: async (value: {
    name: string;
    partition: FieldSessionInput["partition"];
    provenance: FieldSessionInput["provenance"];
    environment_notes: string;
    reference_description: string;
  }): Promise<FieldSession> =>
    (
      await result("/field-sessions/from-observation", json("POST", value))
    ).json(),
  example: async (): Promise<FieldSessionInput> =>
    (await result("/field-sessions/example")).json(),
  importSession: async (file: File): Promise<FieldSession> =>
    (await result("/field-sessions/import", fileBody(file))).json(),
  exportSession: async (id: string): Promise<Blob> =>
    (await result(`${sessionPath(id)}/export`)).blob(),
  importReferences: async (id: string, file: File): Promise<FieldSession> =>
    (
      await result(`${sessionPath(id)}/references/import`, fileBody(file))
    ).json(),
  sync: async (id: string, value: SyncConfig): Promise<FieldSession> =>
    (await result(`${sessionPath(id)}/sync`, json("PUT", value))).json(),
  matches: async (id: string, matches: EventMatch[]): Promise<FieldSession> =>
    (
      await result(`${sessionPath(id)}/matches`, json("PUT", { matches }))
    ).json(),
  eligibility: async (id: string): Promise<FieldEligibility> =>
    (await result(`${sessionPath(id)}/eligibility`)).json(),
  annotationMetrics: async (id: string): Promise<Record<string, unknown>> =>
    (await result(`${sessionPath(id)}/annotations/metrics`)).json(),
  evaluate: async (value: FieldEvaluationRequest): Promise<FieldEvaluation> =>
    (await result("/field-evaluation", json("POST", value))).json(),
  exportEvaluation: async (
    value: FieldEvaluationRequest,
    format: "json" | "csv" | "html",
  ): Promise<Blob> =>
    (
      await result(
        `/field-evaluation/export?format=${format}`,
        json("POST", value),
      )
    ).blob(),
};
