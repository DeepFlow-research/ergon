export type ServerDataSource = "harness" | "backend";

export type ServerDataResult<T> =
  | {
      ok: true;
      data: T;
      status: number;
      source: ServerDataSource;
    }
  | {
      ok: false;
      body: unknown;
      status: number;
      source: "backend";
    };

export function backendUnavailable(detail: string, error: unknown): ServerDataResult<never> {
  return {
    ok: false,
    status: 503,
    source: "backend",
    body: {
      detail,
      error: error instanceof Error ? error.message : "Unknown backend fetch failure",
    },
  };
}
