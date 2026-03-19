"use client";

import { useEffect } from "react";
import { registerPushToken } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { getPushTokenForCurrentApp, registerAppServiceWorker, subscribeForegroundMessages } from "@/lib/firebase";

export default function PwaRegistrar() {
  const { user, verified } = useAuth();

  useEffect(() => {
    let active = true;
    let detachForeground: (() => void) | null = null;
    const tokenCacheKey = user ? `daily-podcast:fcm-token:${user.uid}` : null;

    const syncPushToken = async () => {
      if (!user || verified !== "verified") {
        return;
      }

      try {
        const registration = await registerAppServiceWorker();
        if (!registration || typeof Notification === "undefined" || Notification.permission !== "granted") {
          return;
        }

        const token = await getPushTokenForCurrentApp(registration);
        if (!active) {
          return;
        }

        if (!tokenCacheKey || window.localStorage.getItem(tokenCacheKey) !== token) {
          await registerPushToken(token);
          if (tokenCacheKey) {
            window.localStorage.setItem(tokenCacheKey, token);
          }
        }
      } catch (error) {
        console.error("Failed to sync push token", error);
      }
    };

    void syncPushToken();

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void syncPushToken();
      }
    };

    window.addEventListener("focus", syncPushToken);
    document.addEventListener("visibilitychange", handleVisibilityChange);

    void subscribeForegroundMessages((payload) => {
      if (!active || typeof Notification === "undefined" || Notification.permission !== "granted") {
        return;
      }

      void syncPushToken();

      const title = payload.notification?.title ?? "Daily Podcast";
      const body = payload.notification?.body;
      const icon = payload.notification?.icon ?? "/favicon.ico";
      const link = payload.fcmOptions?.link ?? payload.data?.url ?? "/";

      const notification = new Notification(title, { body, icon, data: { url: link } });
      notification.onclick = () => {
        window.focus();
        window.location.assign(link);
      };
    }).then((unsubscribe) => {
      detachForeground = unsubscribe;
    });

    return () => {
      active = false;
      detachForeground?.();
      window.removeEventListener("focus", syncPushToken);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [user, verified]);

  return null;
}
