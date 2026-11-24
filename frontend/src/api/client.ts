import { tokens } from "../auth/tokens";
import { ApiError, parseErrorBody } from "./errors";
import type { Page } from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "/api";

// Django's DefaultRouter routes need a trailing slash. The hand-written path() routes
// (auth, dashboard, reports, damage, users/me) must not have one.
const NO_TRAILING_SLASH = new Set([
  "/auth/login", "/auth/register", "/auth/refresh", "/auth/logout",
  "/users/me", "/damage", "/dashboard",
  "/reports/products", "/reports/purchases", "/reports/sales", "/reports/inventory",
]);

function withSlash(path: string) {
  return path.endsWith("/") || NO_TRAILING_SLASH.has(path) ? path : path + "/";
}

export type Query = Record<string, string | number | boolean | undefined | null>;

interface Options {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  query?: Query;
  /** false for login and refresh, which must not carry (or retry with) a token. */
  auth?: boolean;
}

let onSessionExpired: () => void = () => {};
export function setSessionExpiredHandler(fn: () => void) {
  onSessionExpired = fn;
}

// Several requests can 401 at once when the access token expires. They all wait on one
// refresh call, so the rotating refresh token is only spent once.
//   ok          new tokens stored
//   rejected    the server said the refresh token is invalid, expired or blacklisted
//   unavailable network failure, throttling (429) or a 5xx: the token may still be fine,
//               so callers must not discard it
export type RefreshResult = "ok" | "rejected" | "unavailable";
let refreshing: Promise<RefreshResult> | null = null;

export function refreshSession(): Promise<RefreshResult> {
  refreshing ??= (async (): Promise<RefreshResult> => {
    const refresh = tokens.refresh;
    if (!refresh) return "rejected";
    try {
      const res = await fetch(BASE + "/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh }),
      });
      if (res.status === 401 || res.status === 400 || res.status === 403) return "rejected";
      if (!res.ok) return "unavailable";
      const data = (await res.json()) as { access: string; refresh?: string };
      tokens.set(data.access, data.refresh);
      return "ok";
    } catch {
      return "unavailable";
    }
  })().finally(() => {
    refreshing = null;
  });
  return refreshing;
}

function buildUrl(path: string, query?: Query) {
  let url = BASE + withSlash(path);
  if (query) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
    }
    const s = qs.toString();
    if (s) url += "?" + s;
  }
  return url;
}

export async function request<T>(path: string, opts: Options = {}, retried = false): Promise<T> {
  const { method = "GET", body, query, auth = true } = opts;
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth && tokens.access) headers.Authorization = `Bearer ${tokens.access}`;

  let res: Response;
  try {
    res = await fetch(buildUrl(path, query), { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check that the API is running.");
  }

  if (res.status === 401 && auth && !retried) {
    const result = await refreshSession();
    if (result === "ok") return request<T>(path, opts, true);
    if (result === "rejected") {
      tokens.clear();
      onSessionExpired();
      throw new ApiError(401, "Your session has expired. Please sign in again.");
    }
    throw new ApiError(503, "Could not refresh your session right now. Try again in a moment.");
  }

  if (res.status === 204) return undefined as T;
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    /* empty or non-JSON body */
  }
  if (!res.ok) throw parseErrorBody(res.status, data);
  return data as T;
}

export const get = <T>(path: string, query?: Query) => request<T>(path, { query });
export const post = <T>(path: string, body?: unknown, auth = true) => request<T>(path, { method: "POST", body: body ?? {}, auth });
export const patch = <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body: body ?? {} });
export const del = <T = void>(path: string) => request<T>(path, { method: "DELETE" });

export const getPage = <T>(path: string, query?: Query) => get<Page<T>>(path, query);
