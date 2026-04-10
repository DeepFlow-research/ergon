import { config } from "@/lib/config";

export async function fetchErgonApi(path: string, init?: RequestInit): Promise<Response> {
  const url = new URL(
    path,
    config.ergonApiBaseUrl.endsWith("/") ? config.ergonApiBaseUrl : `${config.ergonApiBaseUrl}/`,
  );
  return fetch(url, {
    ...init,
    cache: "no-store",
    signal: init?.signal ?? AbortSignal.timeout(5000),
    headers: {
      Accept: "application/json",
      ...(init?.headers ?? {}),
    },
  });
}
