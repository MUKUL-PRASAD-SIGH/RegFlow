"use client";

import { toast } from "@/hooks/use-toast";

type GetToken = (options?: { template?: string }) => Promise<string | null>;

type ApiClientOptions = {
  baseUrl?: string;
  getToken: GetToken;
};

type ApiError = Error & { status?: number; body?: unknown };

async function request<T>(
  method: string,
  url: string,
  getToken: GetToken,
  body?: unknown
): Promise<T> {
  const token = await getToken();
  const res = await fetch(url, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });

  const text = await res.text();
  const parsed = text ? (safeJsonParse(text) ?? text) : null;

  if (!res.ok) {
    const err: ApiError = new Error(typeof parsed === "string" ? parsed : "API request failed");
    err.status = res.status;
    err.body = parsed;
    toast({
      title: `API Error (${res.status})`,
      description: typeof parsed === "string" ? parsed : "Request failed. Check API logs.",
      variant: "destructive",
    });
    throw err;
  }

  return parsed as T;
}

function safeJsonParse(input: string): unknown | null {
  try {
    return JSON.parse(input);
  } catch {
    return null;
  }
}

export function createApiClient({ baseUrl, getToken }: ApiClientOptions) {
  const root = baseUrl ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const join = (path: string) => `${root.replace(/\/$/, "")}${path.startsWith("/") ? "" : "/"}${path}`;

  return {
    get: <T,>(path: string) => request<T>("GET", join(path), getToken),
    post: <T,>(path: string, body?: unknown) => request<T>("POST", join(path), getToken, body),
    put: <T,>(path: string, body?: unknown) => request<T>("PUT", join(path), getToken, body),
    delete: <T,>(path: string) => request<T>("DELETE", join(path), getToken),
  };
}

