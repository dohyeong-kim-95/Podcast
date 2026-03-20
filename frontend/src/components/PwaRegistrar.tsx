"use client";

import { useEffect } from "react";
import { registerPushSubscription } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { getPushSubscriptionForCurrentApp, registerAppServiceWorker } from "@/lib/web-push";

export default function PwaRegistrar() {
  const { user, verified } = useAuth();

  useEffect(() => {
    let active = true;
    const subscriptionCacheKey = user ? `daily-podcast:push-subscription:${user.id}` : null;

    const syncPushToken = async () => {
      if (!user || verified !== "verified") {
        return;
      }

      try {
        const registration = await registerAppServiceWorker();
        if (!registration || typeof Notification === "undefined" || Notification.permission !== "granted") {
          return;
        }

        const subscription = await getPushSubscriptionForCurrentApp(registration);
        if (!active) {
          return;
        }

        const serialized = JSON.stringify(subscription);
        if (!subscriptionCacheKey || window.localStorage.getItem(subscriptionCacheKey) !== serialized) {
          await registerPushSubscription(subscription);
          if (subscriptionCacheKey) {
            window.localStorage.setItem(subscriptionCacheKey, serialized);
          }
        }
      } catch (error) {
        console.error("Failed to sync push subscription", error);
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

    return () => {
      active = false;
      window.removeEventListener("focus", syncPushToken);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [user, verified]);

  return null;
}
