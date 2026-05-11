import { config } from "@/lib/config";

type FetchErgonApiInit = RequestInit & {
  timeoutMs?: number;
};

export async function fetchErgonApi(
  path: string,
  init: FetchErgonApiInit = {},
): Promise<Response> {
  const { timeoutMs = 5_000, ...requestInit } = init;
  const url = new URL(
    path,
    config.ergonApiBaseUrl.endsWith("/") ? config.ergonApiBaseUrl : `${config.ergonApiBaseUrl}/`,
  );
  return fetch(url, {
    ...requestInit,
    cache: "no-store",
    signal: requestInit.signal ?? AbortSignal.timeout(timeoutMs),
    headers: {
      Accept: "application/json",
      ...(requestInit.headers ?? {}),
    },
  });
}
