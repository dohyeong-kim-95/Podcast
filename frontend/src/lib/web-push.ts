"use client";

const SERVICE_WORKER_PATH = "/sw.js";
const WEB_PUSH_PUBLIC_KEY = process.env.NEXT_PUBLIC_WEB_PUSH_PUBLIC_KEY;
const INVALID_PUBLIC_KEY_ERROR =
  "NEXT_PUBLIC_WEB_PUSH_PUBLIC_KEY 형식이 잘못되었습니다. Vercel 환경 변수의 공백, 줄바꿈, 따옴표를 제거한 뒤 다시 배포해 주세요.";

export interface PushSubscriptionPayload {
  endpoint: string;
  expirationTime: number | null;
  keys: {
    p256dh: string;
    auth: string;
  };
}

function isPushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof Notification !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window
  );
}

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);

  for (let i = 0; i < rawData.length; i += 1) {
    outputArray[i] = rawData.charCodeAt(i);
  }

  return outputArray;
}

function normalizeWebPushPublicKey(value: string | undefined): string {
  if (!value) {
    throw new Error("NEXT_PUBLIC_WEB_PUSH_PUBLIC_KEY가 설정되지 않았습니다");
  }

  return value.trim().replace(/^['"]+|['"]+$/g, "").replace(/\s+/g, "");
}

function assertPushConfig(): string {
  const normalized = normalizeWebPushPublicKey(WEB_PUSH_PUBLIC_KEY);

  if (!/^[A-Za-z0-9\-_]+$/.test(normalized)) {
    throw new Error(INVALID_PUBLIC_KEY_ERROR);
  }

  try {
    const decoded = urlBase64ToUint8Array(normalized);
    if (decoded.length !== 65 || decoded[0] !== 0x04) {
      throw new Error(INVALID_PUBLIC_KEY_ERROR);
    }
  } catch {
    throw new Error(INVALID_PUBLIC_KEY_ERROR);
  }

  return normalized;
}

export function formatPushSubscriptionError(error: unknown): string {
  const message = error instanceof Error ? error.message : "알림 활성화에 실패했습니다";
  if (message.includes("applicationServerKey") || message === INVALID_PUBLIC_KEY_ERROR) {
    return INVALID_PUBLIC_KEY_ERROR;
  }
  return message;
}

function serializeSubscription(subscription: PushSubscription): PushSubscriptionPayload {
  const json = subscription.toJSON();
  const p256dh = json.keys?.p256dh;
  const auth = json.keys?.auth;

  if (!json.endpoint || !p256dh || !auth) {
    throw new Error("브라우저 PushSubscription 정보를 직렬화하지 못했습니다");
  }

  return {
    endpoint: json.endpoint,
    expirationTime: json.expirationTime ?? null,
    keys: {
      p256dh,
      auth,
    },
  };
}

export async function registerAppServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!isPushSupported()) {
    return null;
  }

  const existing = await navigator.serviceWorker.getRegistration("/");
  if (existing) {
    return existing;
  }

  return navigator.serviceWorker.register(SERVICE_WORKER_PATH, { scope: "/" });
}

export async function getNotificationPermissionState(): Promise<NotificationPermission | "unsupported"> {
  if (!isPushSupported()) {
    return "unsupported";
  }

  return Notification.permission;
}

export async function getPushSubscriptionForCurrentApp(
  serviceWorkerRegistration?: ServiceWorkerRegistration | null,
): Promise<PushSubscriptionPayload> {
  const registration = serviceWorkerRegistration ?? (await registerAppServiceWorker());
  if (!registration) {
    throw new Error("이 브라우저는 푸시 알림을 지원하지 않습니다");
  }

  let permission = Notification.permission;
  if (permission === "default") {
    permission = await Notification.requestPermission();
  }

  if (permission !== "granted") {
    if (permission === "denied") {
      throw new Error("알림 권한이 거부되었습니다");
    }
    throw new Error("알림 권한이 필요합니다");
  }

  const publicKey = assertPushConfig();
  const existing = await registration.pushManager.getSubscription();
  if (existing) {
    return serializeSubscription(existing);
  }

  const created = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(publicKey) as BufferSource,
  });

  return serializeSubscription(created);
}
