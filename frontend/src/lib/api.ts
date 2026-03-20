import { getSupabaseAccessToken } from "./supabase";
import type { PushSubscriptionPayload } from "./web-push";

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_BASE ||
  "http://localhost:8080"
).replace(/\/+$/, "");

async function getAuthHeaders(): Promise<Record<string, string>> {
  const token = await getSupabaseAccessToken();
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

export async function apiGet<T>(path: string): Promise<T> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}${path}`, { headers });
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
  return res.json();
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
  return res.json();
}

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "PUT",
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
  return res.json();
}

export async function apiDelete<T>(path: string): Promise<T> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "DELETE",
    headers,
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
  return res.json();
}

export async function apiUpload<T>(
  path: string,
  file: File,
  onProgress?: (uploadedBytes: number) => void,
): Promise<T> {
  const token = await getSupabaseAccessToken();
  const formData = new FormData();
  formData.append("file", file);

  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}${path}`);
    xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.responseType = "json";

    xhr.upload.onprogress = (event) => {
      if (!onProgress || !event.lengthComputable) {
        return;
      }

      onProgress(Math.min(file.size, event.loaded));
    };

    xhr.onload = () => {
      let response = xhr.response;
      if (response === null || response === undefined) {
        if (xhr.responseText) {
          try {
            response = JSON.parse(xhr.responseText);
          } catch {
            response = xhr.responseText;
          }
        } else {
          response = null;
        }
      }

      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(response as T);
        return;
      }

      const message =
        typeof response === "string"
          ? response
          : response && typeof response === "object" && "detail" in response
            ? String(response.detail)
            : xhr.responseText || `API error: ${xhr.status}`;
      reject(new Error(message));
    };

    xhr.onerror = () => {
      reject(new Error("Network error"));
    };

    xhr.send(formData);
  });
}

export async function verifyAuth(): Promise<{ uid: string; email: string; name: string }> {
  return apiPost("/api/auth/verify");
}

// Source APIs
export interface Source {
  sourceId: string;
  fileName: string;
  originalType: string;
  convertedType: string | null;
  originalStoragePath: string;
  convertedStoragePath: string | null;
  uploadedAt: string;
  windowDate: string;
  status: string;
}

export async function uploadSource(
  file: File,
  onProgress?: (uploadedBytes: number) => void,
): Promise<Source> {
  return apiUpload("/api/sources/upload", file, onProgress);
}

export async function listSources(date?: string): Promise<{ date: string; sources: Source[] }> {
  const query = date ? `?date=${date}` : "";
  return apiGet(`/api/sources${query}`);
}

export async function deleteSource(sourceId: string): Promise<{ deleted: boolean }> {
  return apiDelete(`/api/sources/${sourceId}`);
}

// Podcast APIs
export interface Podcast {
  podcastId: string;
  uid: string;
  date: string;
  status: string; // "completed" | "generating" | "failed" | "no_sources" | "pending" | "retry_1" | "retry_2"
  audioPath?: string;
  audioUrl?: string;
  durationSeconds?: number;
  feedback?: string | null;
  downloaded?: boolean;
  error?: string | null;
  generatedAt?: string;
  sourceCount?: number;
}

export interface TodayPodcastResponse {
  podcast: Podcast | null;
  date: string;
}

export async function getTodayPodcast(): Promise<TodayPodcastResponse> {
  return apiGet("/api/podcasts/today");
}

export async function submitFeedback(podcastId: string, rating: string): Promise<{ podcastId: string; feedback: string }> {
  return apiPost(`/api/podcasts/${podcastId}/feedback`, { rating });
}

export async function markDownloaded(podcastId: string): Promise<void> {
  return apiPost(`/api/podcasts/${podcastId}/downloaded`);
}

export async function triggerGenerate(): Promise<{ status: string; date: string; podcastId: string }> {
  return apiPost("/api/generate/me");
}

export interface FeedbackHistoryItem {
  date: string;
  rating: string;
}

export interface MemorySettings {
  interests: string;
  tone: string;
  depth: string;
  custom: string;
  feedbackHistory: FeedbackHistoryItem[];
}

export interface MemoryUpdate {
  interests: string;
  tone: string;
  depth: string;
  custom: string;
}

export async function getMemory(): Promise<MemorySettings> {
  return apiGet("/api/memory");
}

export async function updateMemory(memory: MemoryUpdate): Promise<MemorySettings> {
  return apiPut("/api/memory", memory);
}

export type NbSessionState = "valid" | "expiring_soon" | "expired" | "missing";
export type NbAuthSessionState = "pending" | "completed" | "failed" | "timed_out";

export interface NbAuthSessionStatus {
  sessionId: string;
  status: NbAuthSessionState;
  viewerUrl?: string | null;
  authFlow?: string | null;
  error?: string | null;
  completedAt?: string | null;
}

export interface NbSessionStatusResponse {
  status: NbSessionState;
  authFlow?: string | null;
  expiresAt?: string | null;
  lastUpdated?: string | null;
  authSession?: NbAuthSessionStatus | null;
}

export interface StartNbSessionAuthResponse extends NbAuthSessionStatus {
  viewerUrl: string;
}

export async function getNbSessionStatus(): Promise<NbSessionStatusResponse> {
  return apiGet("/api/nb-session/status");
}

export async function startNbSessionAuth(): Promise<StartNbSessionAuthResponse> {
  return apiPost("/api/nb-session/start-auth");
}

export async function pollNbSessionAuth(sessionId: string): Promise<NbAuthSessionStatus> {
  return apiGet(`/api/nb-session/poll/${sessionId}`);
}

export interface RegisterPushSubscriptionResponse {
  registered: boolean;
}

export async function registerPushSubscription(
  subscription: PushSubscriptionPayload,
): Promise<RegisterPushSubscriptionResponse> {
  return apiPost("/api/push-token", { subscription });
}
