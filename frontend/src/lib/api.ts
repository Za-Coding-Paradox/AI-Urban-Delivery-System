// src/lib/api.ts
//
// Typed fetch wrappers for every backend REST endpoint.
// All functions go through the Vite proxy (/api → http://localhost:8000).
//
// Design: thin wrappers — no caching, no retry, no state. Those concerns
// belong in the hooks and store that call these functions. This file only
// knows about the HTTP contract: what to send, what comes back, what errors
// look like.
//
// Every function throws on non-2xx responses with a descriptive message.
// Callers handle errors with try/catch.

import { API_BASE } from "@/lib/constants";
import type {
  CityProfile,
  GenerateProfileRequest,
  RunRequest,
  RunResponse,
  RunResultsResponse,
  RunStatus,
} from "@/types";

// ── internal helpers ───────────────────────────────────────────────────────

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    // Try to extract the backend error message, fall back to HTTP status text
    let message = `HTTP ${response.status}: ${response.statusText}`;
    try {
      const body = await response.json();
      if (body.error) message = body.error;
    } catch {
      // body wasn't JSON — use the status text message above
    }
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

// ── health ─────────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: "ok";
  ws_clients: number;
  active_runs: number;
  bus_buffer_size: number;
}

export async function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

// ── profiles ───────────────────────────────────────────────────────────────

export async function listProfiles(): Promise<string[]> {
  const data = await request<{ profiles: string[] }>("/profiles");
  return data.profiles;
}

export async function getProfile(name: string): Promise<CityProfile> {
  const data = await request<{ profile: CityProfile }>(`/profiles/${name}`);
  return data.profile;
}

export async function generateProfile(req: GenerateProfileRequest): Promise<CityProfile> {
  const data = await request<{ profile: CityProfile }>("/profiles/generate", {
    method: "POST",
    body: JSON.stringify(req),
  });
  return data.profile;
}

export async function saveProfile(name: string, profile: CityProfile): Promise<void> {
  await request<{ saved: string; path: string }>(`/profiles/${name}/save`, {
    method: "POST",
    body: JSON.stringify({ profile }),
  });
}

// ── runs ───────────────────────────────────────────────────────────────────

export async function startRun(req: RunRequest): Promise<RunResponse> {
  return request<RunResponse>("/run", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function getRunStatus(runId: string): Promise<{ run_id: string; status: RunStatus }> {
  return request(`/run/${runId}/status`);
}

export async function getRunResults(runId: string): Promise<RunResultsResponse> {
  return request<RunResultsResponse>(`/run/${runId}/results`);
}

// ── bus buffer ─────────────────────────────────────────────────────────────

export interface BusBufferResponse {
  total: number;
  offset: number;
  limit: number;
  events: unknown[];
}

export async function getBusBuffer(
  limit = 100,
  offset = 0
): Promise<BusBufferResponse> {
  return request<BusBufferResponse>(`/bus/buffer?limit=${limit}&offset=${offset}`);
}
