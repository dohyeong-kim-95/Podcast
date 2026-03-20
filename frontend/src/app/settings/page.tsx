"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import ProtectedRoute from "@/components/ProtectedRoute";
import StatusBanner from "@/components/StatusBanner";
import { useAuth } from "@/lib/auth-context";
import {
  getNbSessionStatus,
  pollNbSessionAuth,
  registerPushSubscription,
  startNbSessionAuth,
  type NbAuthSessionStatus,
  type NbSessionStatusResponse,
} from "@/lib/api";
import {
  formatPushSubscriptionError,
  getNotificationPermissionState,
  getPushSubscriptionForCurrentApp,
  registerAppServiceWorker,
} from "@/lib/web-push";

export default function SettingsPage() {
  return (
    <ProtectedRoute>
      <SettingsContent />
    </ProtectedRoute>
  );
}

function SettingsContent() {
  const { user } = useAuth();
  const router = useRouter();
  const [session, setSession] = useState<NbSessionStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [sessionNotice, setSessionNotice] = useState<string | null>(null);
  const [pollSessionId, setPollSessionId] = useState<string | null>(null);
  const [notificationPermission, setNotificationPermission] = useState<NotificationPermission | "unsupported" | "checking">("checking");
  const [notificationEndpoint, setNotificationEndpoint] = useState<string | null>(null);
  const [notificationError, setNotificationError] = useState<string | null>(null);
  const [notificationNotice, setNotificationNotice] = useState<string | null>(null);
  const [notificationSaving, setNotificationSaving] = useState(false);
  const [notificationPromptArmed, setNotificationPromptArmed] = useState(false);
  const subscriptionCacheKey = user ? `daily-podcast:push-subscription:${user.id}` : null;

  const refreshStatus = useCallback(async () => {
    try {
      const result = await getNbSessionStatus();
      setSession(result);
      setSessionError(null);
      if (result.authSession?.status === "pending") {
        setPollSessionId(result.authSession.sessionId);
      } else {
        setPollSessionId(null);
      }
    } catch {
      setSessionError("세션 상태를 불러오지 못했습니다");
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshNotificationState = useCallback(async () => {
    const permission = await getNotificationPermissionState();
    setNotificationPermission(permission);

    if (typeof window === "undefined" || permission !== "granted") {
      setNotificationEndpoint(null);
      return;
    }

    const stored = subscriptionCacheKey ? window.localStorage.getItem(subscriptionCacheKey) : null;
    if (!stored) {
      setNotificationEndpoint(null);
      return;
    }

    try {
      const parsed = JSON.parse(stored) as { endpoint?: string };
      setNotificationEndpoint(parsed.endpoint ?? null);
    } catch {
      setNotificationEndpoint(null);
    }
  }, [subscriptionCacheKey]);

  useEffect(() => {
    refreshStatus();
    void refreshNotificationState();
  }, [refreshNotificationState, refreshStatus]);

  useEffect(() => {
    if (!pollSessionId) {
      return;
    }

    let cancelled = false;

    const tick = async () => {
      try {
        const result = await pollNbSessionAuth(pollSessionId);
        if (cancelled) {
          return;
        }

        setSession((current) =>
          current
            ? {
                ...current,
                authSession: result,
              }
            : {
                status: "missing",
                authSession: result,
              },
        );

        if (result.status === "completed") {
          setSessionNotice("NotebookLM 세션이 저장되었습니다");
          setPollSessionId(null);
          await refreshStatus();
        } else if (result.status === "failed" || result.status === "timed_out") {
          setSessionError(result.error || "재인증에 실패했습니다");
          setPollSessionId(null);
          await refreshStatus();
        }
      } catch {
        if (!cancelled) {
          setSessionError("세션 상태를 확인하지 못했습니다");
          setPollSessionId(null);
        }
      }
    };

    void tick();
    const interval = window.setInterval(() => {
      void tick();
    }, 3000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [pollSessionId, refreshStatus]);

  const handleStartAuth = useCallback(async () => {
    setStarting(true);
    setSessionError(null);
    setSessionNotice(null);

    try {
      const result = await startNbSessionAuth();
      const nextAuthSession: NbAuthSessionStatus = {
        sessionId: result.sessionId,
        status: result.status,
        viewerUrl: result.viewerUrl,
        authFlow: result.authFlow,
        error: result.error,
        completedAt: result.completedAt,
      };

      setSession((current) =>
        current
          ? {
              ...current,
              authSession: nextAuthSession,
            }
          : {
              status: "missing",
              authSession: nextAuthSession,
            },
      );
      setPollSessionId(result.sessionId);

      const popup = window.open(result.viewerUrl, "_blank", "noopener,noreferrer");
      if (!popup) {
        setSessionNotice("브라우저가 새 탭 열기를 차단했습니다. 아래 링크를 눌러 직접 열어주세요.");
      } else {
        setSessionNotice("새 탭에서 NotebookLM 로그인을 완료하면 이 화면이 자동으로 갱신됩니다.");
      }
    } catch (err) {
      const message = formatApiErrorMessage(err, "재인증을 시작하지 못했습니다");
      setSessionError(message);
    } finally {
      setStarting(false);
    }
  }, []);

  const handleEnableNotifications = useCallback(async () => {
    if (notificationPermission === "default" && !notificationPromptArmed) {
      setNotificationError(null);
      setNotificationNotice("다음 단계에서 브라우저 알림 권한 팝업이 열립니다. 실수로 '거부'하면 브라우저 설정에서 직접 다시 허용해야 합니다.");
      setNotificationPromptArmed(true);
      return;
    }

    setNotificationSaving(true);
    setNotificationError(null);
    setNotificationNotice(notificationPermission === "default"
      ? "브라우저 권한 팝업이 열리면 '허용'을 눌러 주세요."
      : null);

    try {
      const registration = await registerAppServiceWorker();
      if (!registration) {
        throw new Error("서비스 워커를 등록하지 못했습니다");
      }

      const subscription = await getPushSubscriptionForCurrentApp(registration);
      await registerPushSubscription(subscription);

      if (typeof window !== "undefined" && subscriptionCacheKey) {
        window.localStorage.setItem(subscriptionCacheKey, JSON.stringify(subscription));
      }

      setNotificationPermission(typeof Notification === "undefined" ? "unsupported" : Notification.permission);
      setNotificationEndpoint(subscription.endpoint);
      setNotificationNotice("알림이 활성화되었습니다. 생성 완료와 리마인더를 받을 수 있습니다.");
      setNotificationPromptArmed(false);
    } catch (err) {
      const message = formatPushSubscriptionError(err);
      setNotificationError(message === "API error: 404" ? "푸시 토큰 등록 API가 아직 연결되지 않았습니다" : message);
      if (typeof Notification !== "undefined" && Notification.permission === "denied") {
        setNotificationNotice("이 사이트 알림이 차단되었습니다. 주소창 왼쪽 사이트 설정에서 알림을 '허용'으로 바꾼 뒤 다시 시도해 주세요.");
      }
      await refreshNotificationState();
    } finally {
      setNotificationSaving(false);
    }
  }, [notificationPermission, notificationPromptArmed, refreshNotificationState, subscriptionCacheKey]);

  const statusTone = useMemo(() => {
    if (!session) {
      return "border-[#282828] bg-[#181818]";
    }
    if (session.authSession?.status === "pending") {
      return "border-sky-800/50 bg-sky-950/20";
    }
    if (session.status === "valid") {
      return "border-emerald-800/40 bg-emerald-950/20";
    }
    if (session.status === "expiring_soon") {
      return "border-amber-800/50 bg-amber-950/20";
    }
    return "border-red-800/40 bg-red-950/20";
  }, [session]);

  return (
    <div className="min-h-screen bg-[#121212] text-white">
      <header className="flex items-center px-4 py-3 border-b border-[#282828]">
        <button
          onClick={() => router.push("/")}
          className="mr-3 text-[#b3b3b3] transition-colors hover:text-white"
          aria-label="뒤로"
          type="button"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div>
          <h1 className="text-lg font-bold">설정</h1>
          <p className="text-xs text-[#b3b3b3]">NotebookLM 세션과 알림 상태 관리</p>
        </div>
      </header>

      <main className="mx-auto max-w-lg space-y-4 px-4 py-6">
        <StatusBanner session={session} />

        {loading ? (
          <div className="rounded-xl bg-[#181818] p-6 text-center">
            <div className="mx-auto mb-3 h-8 w-8 rounded-full border-2 border-[#1DB954] border-t-transparent animate-spin" />
            <p className="text-sm text-[#b3b3b3]">세션 상태를 불러오는 중...</p>
          </div>
        ) : (
          <section className={`rounded-xl border p-4 ${statusTone}`}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold">현재 상태</p>
                <p className="mt-1 text-2xl font-bold">{statusLabel(session?.status)}</p>
                <p className="mt-2 text-xs text-[#b3b3b3]">
                  {session?.expiresAt
                    ? `예상 만료 시각: ${new Date(session.expiresAt).toLocaleString("ko-KR")}`
                    : "저장된 세션이 없거나 만료 시각을 확인할 수 없습니다."}
                </p>
                {session?.lastUpdated && (
                  <p className="mt-1 text-xs text-[#6f6f6f]">
                    마지막 갱신: {new Date(session.lastUpdated).toLocaleString("ko-KR")}
                  </p>
                )}
              </div>
              <span className="rounded-full bg-white/5 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#b3b3b3]">
                {session?.authFlow ?? "new_tab"}
              </span>
            </div>
          </section>
        )}

        <section className="space-y-3 rounded-xl bg-[#181818] p-4">
          <div>
            <p className="text-sm font-semibold">재인증</p>
            <p className="mt-1 text-xs text-[#b3b3b3]">
              새 탭에서 NotebookLM 로그인을 완료하면 세션이 자동 저장됩니다.
            </p>
          </div>

          {session?.authSession?.viewerUrl && session.authSession.status === "pending" && (
            <Link
              href={session.authSession.viewerUrl}
              target="_blank"
              rel="noreferrer"
              className="block rounded-lg border border-[#282828] px-4 py-3 text-sm text-[#9ad8ff] hover:border-sky-700/50"
            >
              재인증 탭 다시 열기
            </Link>
          )}

          {sessionNotice && (
            <div className="rounded-lg border border-emerald-800/40 bg-emerald-950/20 px-4 py-3 text-sm text-emerald-200">
              {sessionNotice}
            </div>
          )}

          {sessionError && (
            <div className="rounded-lg border border-red-800/40 bg-red-950/20 px-4 py-3 text-sm text-red-300">
              {sessionError}
            </div>
          )}

          <button
            type="button"
            onClick={handleStartAuth}
            disabled={starting || session?.authSession?.status === "pending"}
            className="w-full rounded-full bg-[#1DB954] py-3 text-sm font-semibold text-black transition-colors hover:bg-[#1ed760] disabled:opacity-50"
          >
            {starting || session?.authSession?.status === "pending" ? "재인증 준비 중..." : "새 탭에서 재인증"}
          </button>
        </section>

        <section className="space-y-3 rounded-xl bg-[#181818] p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold">푸시 알림</p>
              <p className="mt-1 text-xs text-[#b3b3b3]">
                생성 완료와 다운로드 리마인더를 모바일 알림으로 받을 수 있습니다.
              </p>
            </div>
            <span className={`rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] ${
              notificationPermission === "granted"
                ? "bg-emerald-950/40 text-emerald-200"
                : notificationPermission === "denied"
                  ? "bg-red-950/40 text-red-200"
                  : notificationPermission === "unsupported"
                    ? "bg-[#282828] text-[#8a8a8a]"
                    : "bg-amber-950/40 text-amber-200"
            }`}>
              {notificationPermissionLabel(notificationPermission)}
            </span>
          </div>

          {notificationEndpoint && (
            <div className="rounded-lg border border-[#282828] bg-[#121212] px-4 py-3 text-xs text-[#b3b3b3]">
              등록된 엔드포인트: <span className="text-[#d7d7d7]">{maskValue(notificationEndpoint)}</span>
            </div>
          )}

          {notificationNotice && (
            <div className="rounded-lg border border-emerald-800/40 bg-emerald-950/20 px-4 py-3 text-sm text-emerald-200">
              {notificationNotice}
            </div>
          )}

          {notificationError && (
            <div className="rounded-lg border border-red-800/40 bg-red-950/20 px-4 py-3 text-sm text-red-300">
              {notificationError}
            </div>
          )}

          {notificationPermission === "denied" && (
            <div className="rounded-lg border border-[#282828] bg-[#121212] px-4 py-3 text-xs text-[#b3b3b3] space-y-2">
              <p>브라우저가 이 사이트의 알림을 차단했습니다.</p>
              <p>복구 방법: 주소창 왼쪽 사이트 정보 아이콘 &gt; 사이트 설정 &gt; 알림 &gt; 허용</p>
              <p className="text-[#8f8f8f]">대상 사이트: {typeof window !== "undefined" ? window.location.origin : "https://podcast.bubblelab.dev"}</p>
            </div>
          )}

          <button
            type="button"
            onClick={handleEnableNotifications}
            disabled={notificationSaving || notificationPermission === "unsupported"}
            className="w-full rounded-full border border-[#1DB954]/40 bg-[#1DB954]/10 py-3 text-sm font-semibold text-[#9ef0b7] transition-colors hover:bg-[#1DB954]/20 disabled:opacity-50"
          >
            {notificationSaving
              ? "알림 설정 중..."
              : notificationPermission === "default" && notificationPromptArmed
                ? "브라우저 권한 요청"
              : notificationPermission === "granted"
                ? "알림 다시 동기화"
                : "알림 활성화"}
          </button>
        </section>
      </main>
    </div>
  );
}

function statusLabel(status?: NbSessionStatusResponse["status"]) {
  switch (status) {
    case "valid":
      return "유효";
    case "expiring_soon":
      return "만료 임박";
    case "expired":
      return "만료";
    case "missing":
      return "미설정";
    default:
      return "확인 중";
  }
}

function formatApiErrorMessage(error: unknown, fallback: string): string {
  const message = error instanceof Error ? error.message : fallback;
  if (message === "API error: 401") {
    return "API 인증에 실패했습니다. 다시 로그인해 보고, 계속되면 Cloud Run 백엔드가 최신 Supabase 코드로 재배포되었는지 확인해 주세요.";
  }
  return message;
}

function notificationPermissionLabel(permission: NotificationPermission | "unsupported" | "checking") {
  switch (permission) {
    case "granted":
      return "enabled";
    case "denied":
      return "blocked";
    case "unsupported":
      return "unsupported";
    default:
      return "pending";
  }
}

function maskValue(value: string) {
  if (value.length <= 12) {
    return value;
  }

  return `${value.slice(0, 8)}...${value.slice(-8)}`;
}
