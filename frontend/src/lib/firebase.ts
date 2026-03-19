import { initializeApp, getApps, type FirebaseApp } from "firebase/app";
import { getAuth, type Auth } from "firebase/auth";
import { getFirestore, type Firestore } from "firebase/firestore";
import {
  getMessaging,
  getToken,
  isSupported,
  onMessage,
  type MessagePayload,
  type Messaging,
  type Unsubscribe,
} from "firebase/messaging";
import { getStorage, type FirebaseStorage } from "firebase/storage";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

let _app: FirebaseApp | undefined;
let _auth: Auth | undefined;
let _db: Firestore | undefined;
let _storage: FirebaseStorage | undefined;
let _messagingPromise: Promise<Messaging | null> | undefined;

const FCM_VAPID_KEY = process.env.NEXT_PUBLIC_FIREBASE_VAPID_KEY;
const SERVICE_WORKER_PATH = "/sw.js";

function getApp(): FirebaseApp {
  if (!_app) {
    _app = getApps().length === 0 ? initializeApp(firebaseConfig) : getApps()[0];
  }
  return _app;
}

export function getFirebaseAuth(): Auth {
  if (!_auth) _auth = getAuth(getApp());
  return _auth;
}

export function getFirebaseDb(): Firestore {
  if (!_db) _db = getFirestore(getApp());
  return _db;
}

export function getFirebaseStorage(): FirebaseStorage {
  if (!_storage) _storage = getStorage(getApp());
  return _storage;
}

export async function registerAppServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (typeof window === "undefined" || !("serviceWorker" in navigator)) {
    return null;
  }

  const existing = await navigator.serviceWorker.getRegistration("/");
  if (existing) {
    return existing;
  }

  return navigator.serviceWorker.register(SERVICE_WORKER_PATH, { scope: "/" });
}

export async function getFirebaseMessagingClient(): Promise<Messaging | null> {
  if (typeof window === "undefined") {
    return null;
  }

  if (!_messagingPromise) {
    _messagingPromise = isSupported()
      .then((supported) => (supported ? getMessaging(getApp()) : null))
      .catch(() => null);
  }

  return _messagingPromise;
}

export async function getNotificationPermissionState(): Promise<NotificationPermission | "unsupported"> {
  if (typeof window === "undefined" || typeof Notification === "undefined") {
    return "unsupported";
  }

  const messaging = await getFirebaseMessagingClient();
  return messaging ? Notification.permission : "unsupported";
}

export async function getPushTokenForCurrentApp(
  serviceWorkerRegistration?: ServiceWorkerRegistration | null,
): Promise<string> {
  const registration = serviceWorkerRegistration ?? (await registerAppServiceWorker());
  const messaging = await getFirebaseMessagingClient();
  if (!registration || !messaging) {
    throw new Error("이 브라우저는 푸시 알림을 지원하지 않습니다");
  }

  if (typeof Notification === "undefined") {
    throw new Error("알림 API를 사용할 수 없습니다");
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

  if (!FCM_VAPID_KEY) {
    throw new Error("NEXT_PUBLIC_FIREBASE_VAPID_KEY가 설정되지 않았습니다");
  }

  const token = await getToken(messaging, {
    serviceWorkerRegistration: registration,
    vapidKey: FCM_VAPID_KEY,
  });

  if (!token) {
    throw new Error("FCM 토큰을 발급하지 못했습니다");
  }

  return token;
}

export async function subscribeForegroundMessages(
  handler: (payload: MessagePayload) => void,
): Promise<Unsubscribe | null> {
  const messaging = await getFirebaseMessagingClient();
  if (!messaging) {
    return null;
  }

  return onMessage(messaging, handler);
}

export default getApp;
