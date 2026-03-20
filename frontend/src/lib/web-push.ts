"use client";

const SERVICE_WORKER_PATH = "/sw.js";
const WEB_PUSH_PUBLIC_KEY = process.env.NEXT_PUBLIC_WEB_PUSH_PUBLIC_KEY;

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

function assertPushConfig(): string {
  if (!WEB_PUSH_PUBLIC_KEY) {
    throw new Error("NEXT_PUBLIC_WEB_PUSH_PUBLIC_KEY가 설정되지 않았습니다");
  }

  return WEB_PUSH_PUBLIC_KEY;
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
