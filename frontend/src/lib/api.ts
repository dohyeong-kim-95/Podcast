import { getFirebaseAuth } from "./firebase";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8080";

async function getAuthHeaders(): Promise<Record<string, string>> {
  const user = getFirebaseAuth().currentUser;
  if (!user) {
    throw new Error("Not authenticated");
  }
  const token = await user.getIdToken();
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

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const user = getFirebaseAuth().currentUser;
  if (!user) {
    throw new Error("Not authenticated");
  }
  const token = await user.getIdToken();
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `API error: ${res.status}`);
  }
  return res.json();
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

export async function uploadSource(file: File): Promise<Source> {
  return apiUpload("/api/sources/upload", file);
}

export async function listSources(date?: string): Promise<{ date: string; sources: Source[] }> {
  const query = date ? `?date=${date}` : "";
  return apiGet(`/api/sources${query}`);
}

export async function deleteSource(sourceId: string): Promise<{ deleted: boolean }> {
  return apiDelete(`/api/sources/${sourceId}`);
}
