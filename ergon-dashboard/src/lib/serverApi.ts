import { config } from "@/lib/config";

export async function fetchArcaneApi(path: string, init?: RequestInit): Promise<Response> {
  const url = new URL(
    path,
    config.arcaneApiBaseUrl.endsWith("/") ? config.arcaneApiBaseUrl : `${config.arcaneApiBaseUrl}/`,
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
