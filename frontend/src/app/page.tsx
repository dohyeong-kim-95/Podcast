"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import ProtectedRoute from "@/components/ProtectedRoute";
import AudioPlayer from "@/components/AudioPlayer";
import FeedbackBar from "@/components/FeedbackBar";
import InstallPrompt from "@/components/InstallPrompt";
import StatusBanner from "@/components/StatusBanner";
import { useAuth } from "@/lib/auth-context";
import {
  getNbSessionStatus,
  getTodayPodcast,
  listSources,
  triggerGenerate,
  type NbSessionStatusResponse,
  type Podcast,
  type Source,
} from "@/lib/api";

export default function Home() {
  return (
    <ProtectedRoute>
      <MainContent />
    </ProtectedRoute>
  );
}

function MainContent() {
  const { user, signOut } = useAuth();
  const [podcast, setPodcast] = useState<Podcast | null>(null);
  const [todaySources, setTodaySources] = useState<Source[]>([]);
  const [nbSession, setNbSession] = useState<NbSessionStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggeringGenerate, setTriggeringGenerate] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lastDebugSignatureRef = useRef<string>("");

  const fetchPodcast = useCallback(async () => {
    try {
      setError(null);
      const [podcastRes, nbSessionRes, sourcesRes] = await Promise.all([
        getTodayPodcast(),
        getNbSessionStatus().catch(() => null),
        listSources().catch(() => ({ date: "", sources: [] as Source[] })),
      ]);
      setPodcast(podcastRes.podcast);
      setNbSession(nbSessionRes);
      setTodaySources(sourcesRes.sources);
    } catch {
      setError("팟캐스트 정보를 불러올 수 없습니다");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPodcast();
  }, [fetchPodcast]);

  useEffect(() => {
    const signature = JSON.stringify({
      loading,
      podcastStatus: podcast?.status ?? null,
      podcastId: podcast?.podcastId ?? null,
      requestedAt: podcast?.requestedAt ?? null,
      generatedAt: podcast?.generatedAt ?? null,
      sourceCount: podcast?.sourceCount ?? null,
      todaySourceCount: todaySources.length,
      nbSessionStatus: nbSession?.status ?? null,
      error,
      triggeringGenerate,
    });

    if (signature === lastDebugSignatureRef.current) {
      return;
    }

    lastDebugSignatureRef.current = signature;
    console.log("[podcast-debug][change]", {
      at: new Date().toISOString(),
      loading,
      podcastStatus: podcast?.status ?? null,
      podcastId: podcast?.podcastId ?? null,
      requestedAt: podcast?.requestedAt ?? null,
      generatedAt: podcast?.generatedAt ?? null,
      sourceCount: podcast?.sourceCount ?? null,
      todaySourceCount: todaySources.length,
      todaySourceSummary: summarizeSources(todaySources).description,
      nbSessionStatus: nbSession?.status ?? null,
      error,
      triggeringGenerate,
    });
  }, [loading, podcast, todaySources, nbSession, error, triggeringGenerate]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      console.log("[podcast-debug][tick]", {
        at: new Date().toISOString(),
        podcastStatus: podcast?.status ?? null,
        podcastId: podcast?.podcastId ?? null,
        requestedAt: podcast?.requestedAt ?? null,
        generatedAt: podcast?.generatedAt ?? null,
        sourceCount: podcast?.sourceCount ?? null,
        todaySourceCount: todaySources.length,
        todaySourceSummary: summarizeSources(todaySources).description,
        nbSessionStatus: nbSession?.status ?? null,
        loading,
        error,
      });
    }, 10000);

    return () => window.clearInterval(interval);
  }, [loading, podcast, todaySources, nbSession, error]);

  // Poll while generating
  useEffect(() => {
    if (!podcast) return;
    const status = podcast.status;
    if (!["generating", "pending"].includes(status)) return;

    const interval = setInterval(fetchPodcast, 5000);
    return () => clearInterval(interval);
  }, [podcast, fetchPodcast]);

  const handleGenerateNow = useCallback(async () => {
    setTriggeringGenerate(true);
    setError(null);
    console.log("[podcast-debug][request]", {
      at: new Date().toISOString(),
      action: "triggerGenerate",
      podcastStatusBefore: podcast?.status ?? null,
      todaySourceCount: todaySources.length,
      todaySourceSummary: summarizeSources(todaySources).description,
      nbSessionStatus: nbSession?.status ?? null,
    });
    try {
      await triggerGenerate();
      await fetchPodcast();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "즉시 생성에 실패했습니다";
      if (msg.includes("once per day") || msg.includes("409")) {
        setError("즉시 생성은 하루에 한 번만 사용할 수 있습니다");
      } else {
        setError(msg);
      }
    } finally {
      setTriggeringGenerate(false);
    }
  }, [fetchPodcast, podcast, todaySources, nbSession]);

  const sessionReady = !nbSession || ["valid", "expiring_soon"].includes(nbSession.status);
  const canRetryToday =
    podcast?.status === "no_sources" ||
    podcast?.status === "failed" ||
    podcast?.status === "retry_1" ||
    podcast?.status === "retry_2";
  const generationActive = !!podcast && ["generating", "pending"].includes(podcast.status);
  const hasTodaySources = todaySources.length > 0;
  const generateRemainingToday = podcast && !canRetryToday ? 0 : 1;
  const generateDisabled =
    loading ||
    triggeringGenerate ||
    generationActive ||
    (!canRetryToday && !!podcast) ||
    !sessionReady ||
    !hasTodaySources;
  const generateHint = !sessionReady
    ? "NotebookLM 재인증 후 사용할 수 있습니다"
    : !hasTodaySources
      ? "업로드 탭의 오늘 소스가 아직 없습니다"
    : generationActive
      ? "지금 생성이 진행 중입니다"
      : podcast?.status === "completed"
        ? "오늘 사용이 끝났습니다"
        : podcast?.status === "no_sources"
          ? "지금 올린 소스로 다시 시도할 수 있습니다"
          : podcast?.status === "failed"
            ? "오류를 확인한 뒤 다시 시도할 수 있습니다"
            : "오늘 한 번만 바로 생성할 수 있습니다";

  return (
    <div className="min-h-screen bg-[#121212] text-white">
      <header className="sticky top-0 z-10 border-b border-[#282828] bg-[#121212]/95 px-4 py-3 backdrop-blur">
        <h1 className="text-lg font-bold">Daily Podcast</h1>
        <button
          onClick={signOut}
          type="button"
          className="min-h-10 rounded-full px-3 text-sm text-[#b3b3b3] transition-colors hover:bg-white/5 hover:text-white"
        >
          로그아웃
        </button>
      </header>

      <main className="mx-auto max-w-lg space-y-4 px-4 py-6">
        <div className="mb-2">
          <p className="text-[#b3b3b3] text-sm">
            {user?.displayName || user?.email}님, 안녕하세요
          </p>
        </div>

        <StatusBanner session={nbSession} />
        <InstallPrompt />

        {error && (
          <div className="bg-red-900/30 border border-red-800 rounded-lg px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {loading ? (
          <LoadingState />
        ) : podcast?.status === "completed" && podcast.audioUrl ? (
          <CompletedState podcast={podcast} />
        ) : podcast && ["generating", "pending"].includes(podcast.status) ? (
          <GeneratingState podcast={podcast} />
        ) : hasTodaySources ? (
          <ReadyToGenerateState sources={todaySources} podcastStatus={podcast?.status} />
        ) : podcast?.status === "failed" ? (
          <FailedState />
        ) : podcast?.status === "no_sources" ? (
          <NoSourcesState />
        ) : (
          <EmptyState />
        )}

        <Link
          href="/upload"
          className="flex items-center justify-center gap-2 w-full bg-[#1DB954] text-black font-semibold py-3 rounded-full hover:bg-[#1ed760] transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          소스 업로드
        </Link>

        <button
          type="button"
          onClick={handleGenerateNow}
          disabled={generateDisabled}
          className={`w-full rounded-2xl border px-4 py-3 text-left transition-colors ${
            generateDisabled
              ? "border-[#282828] bg-[#181818] text-[#6f6f6f]"
              : "border-[#1DB954]/40 bg-[#16231b] text-white hover:border-[#1DB954] hover:bg-[#1a2b20]"
          }`}
        >
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white/10">
                {triggeringGenerate ? (
                  <div className="h-5 w-5 rounded-full border-2 border-current border-t-transparent animate-spin" />
                ) : (
                  <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 3 4 14h6l-1 7 9-11h-6l1-7z" />
                  </svg>
                )}
              </div>
              <div>
                <p className="font-semibold">즉시 팟캐스트 생성</p>
                <p className="text-xs opacity-70">{generateHint}</p>
              </div>
            </div>
            <span className="rounded-full border border-current/20 px-3 py-1 text-xs font-semibold">
              {generateRemainingToday}/1
            </span>
          </div>
        </button>

        <div className="grid grid-cols-2 gap-3">
          <Link
            href="/memory"
            className="flex items-center justify-center gap-2 bg-[#181818] border border-[#282828] text-white font-semibold py-3 rounded-full hover:border-[#1DB954] transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.75a2.25 2.25 0 100 4.5 2.25 2.25 0 000-4.5z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6.94 4.94l1.06 1.06m8 8 1.06 1.06M4.94 17.06 6 16m12-8 1.06-1.06M12 2.25v1.5m0 16.5v1.5M2.25 12h1.5m16.5 0h1.5" />
            </svg>
            메모리 설정
          </Link>

          <Link
            href="/settings"
            className="flex items-center justify-center gap-2 bg-[#181818] border border-[#282828] text-white font-semibold py-3 rounded-full hover:border-[#1DB954] transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317a1 1 0 011.35-.936l.094.04 1.304.652a1 1 0 00.894 0l1.304-.652a1 1 0 011.444.894v1.46a1 1 0 00.293.707l1.033 1.033a1 1 0 010 1.414l-1.033 1.033a1 1 0 00-.293.707v1.46a1 1 0 01-1.444.894l-1.304-.652a1 1 0 00-.894 0l-1.304.652a1 1 0 01-1.444-.894v-1.46a1 1 0 00-.293-.707L5.34 9.581a1 1 0 010-1.414l1.033-1.033a1 1 0 00.293-.707v-1.46a1 1 0 011.444-.894l1.304.652a1 1 0 00.894 0l.017-.008z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 11.25A2.25 2.25 0 1012 6.75a2.25 2.25 0 000 4.5z" />
            </svg>
            설정
          </Link>
        </div>
      </main>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="bg-[#181818] rounded-xl p-6 text-center">
      <div className="w-8 h-8 mx-auto mb-3 border-2 border-[#1DB954] border-t-transparent rounded-full animate-spin" />
      <p className="text-[#b3b3b3] text-sm">불러오는 중...</p>
    </div>
  );
}

function CompletedState({ podcast }: { podcast: Podcast }) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 mb-1">
        <div className="w-8 h-8 rounded-full bg-[#1DB954] flex items-center justify-center">
          <svg className="w-4 h-4 text-black" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55C7.79 13 6 14.79 6 17s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z" />
          </svg>
        </div>
        <div>
          <p className="text-sm font-semibold">오늘의 팟캐스트</p>
          <p className="text-[10px] text-[#b3b3b3]">
            {podcast.sourceCount}개 소스 · {podcast.durationSeconds ? formatDuration(podcast.durationSeconds) : ""}
          </p>
        </div>
      </div>

      <AudioPlayer
        audioUrl={podcast.audioUrl!}
        podcastId={podcast.podcastId}
        durationSeconds={podcast.durationSeconds}
      />

      <FeedbackBar
        podcastId={podcast.podcastId}
        currentFeedback={podcast.feedback}
      />
    </div>
  );
}

function GeneratingState({ podcast }: { podcast: Podcast }) {
  const statusLabel =
    podcast.status === "retry_1" || podcast.status === "retry_2"
      ? "재시도 중"
      : podcast.status === "pending"
        ? "대기 중"
        : "진행 중";
  const requestTime = formatRequestTime(podcast.requestedAt);

  return (
    <div className="podcast-generating-shell rounded-[28px] p-[1px]">
      <div className="relative rounded-[27px] bg-[#181818] px-5 py-5">
        <div className="mb-4 flex items-start justify-between gap-4">
          <div className="space-y-1">
            <p className="text-base font-semibold text-white">팟캐스트 생성 중</p>
            <p className="text-xs text-[#8e8e8e]">
              요청 시간 : {requestTime}
            </p>
          </div>
          <span className="rounded-full border border-[#1DB954]/25 bg-[#112117] px-3 py-1 text-[11px] font-semibold text-[#7ee2a0]">
            {statusLabel}
          </span>
        </div>

        <div className="space-y-2 text-sm leading-6 text-[#d2d2d2]">
          <p>NotebookLM에서 소스를 정리하고 오디오를 만드는 중입니다.</p>
          <p className="text-[#9a9a9a]">
            보통 3~10분 정도 걸리고, 길면 20분 안쪽까지 소요될 수 있습니다.
          </p>
          <p className="text-[#7e7e7e]">
            완료되면 이 화면이 자동으로 갱신됩니다.
          </p>
        </div>
      </div>
    </div>
  );
}

function FailedState() {
  return (
    <div className="bg-[#181818] rounded-xl p-6 text-center">
      <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-[#282828] flex items-center justify-center">
        <svg className="w-6 h-6 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
        </svg>
      </div>
      <p className="text-white text-sm font-medium">팟캐스트 생성에 실패했습니다</p>
      <p className="text-[#535353] text-xs mt-1">
        세션이나 생성 과정에서 오류가 발생했습니다. 설정과 소스를 확인한 뒤 다시 시도해 보세요.
      </p>
    </div>
  );
}

function NoSourcesState() {
  return (
    <div className="bg-[#181818] rounded-xl p-6 text-center">
      <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-[#282828] flex items-center justify-center">
        <svg className="w-6 h-6 text-[#b3b3b3]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
      </div>
      <p className="text-white text-sm font-medium">오늘 생성에 포함된 소스가 없습니다</p>
      <p className="text-[#535353] text-xs mt-1">
        이전 생성 시점에는 사용할 수 있는 소스가 없었습니다. 지금 파일을 올렸다면 아래 요약 카드와 즉시 생성 버튼에서 반영 여부를 확인할 수 있습니다.
      </p>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="bg-[#181818] rounded-xl p-6 text-center">
      <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-[#282828] flex items-center justify-center">
        <svg className="w-6 h-6 text-[#b3b3b3]" fill="currentColor" viewBox="0 0 24 24">
          <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55C7.79 13 6 14.79 6 17s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z" />
        </svg>
      </div>
      <p className="text-[#b3b3b3] text-sm">
        오늘의 팟캐스트가 아직 없습니다
      </p>
      <p className="text-[#535353] text-xs mt-1">
        소스를 업로드하면 매일 아침 팟캐스트가 생성됩니다
      </p>
    </div>
  );
}

function ReadyToGenerateState({
  sources,
  podcastStatus,
}: {
  sources: Source[];
  podcastStatus?: string;
}) {
  const summary = summarizeSources(sources);
  const helper =
    podcastStatus === "failed" || podcastStatus === "retry_1" || podcastStatus === "retry_2"
      ? "이전 생성은 실패했지만, 현재 업로드된 소스로 다시 시도할 수 있습니다."
      : podcastStatus === "no_sources"
        ? "이전 생성 시점에는 소스가 없었지만, 지금은 다시 시도할 수 있습니다."
        : "즉시 생성 버튼을 누르면 현재 업로드된 소스로 바로 테스트할 수 있습니다.";

  return (
    <div className="rounded-xl border border-[#2a332d] bg-[#181d19] px-5 py-5">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <p className="text-sm font-semibold text-white">오늘 생성에 포함될 소스</p>
          <p className="text-sm leading-6 text-[#d9d9d9]">{summary.description}</p>
          <p className="text-xs text-[#8d8d8d]">{helper}</p>
        </div>
        <span className="rounded-full border border-[#1DB954]/20 bg-[#132117] px-3 py-1 text-xs font-semibold text-[#86dba2]">
          {sources.length}개
        </span>
      </div>
    </div>
  );
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m === 0) return `${s}초`;
  if (s === 0) return `${m}분`;
  return `${m}분 ${s}초`;
}

function summarizeSources(sources: Source[]): { description: string } {
  if (sources.length === 0) {
    return {
      description: "업로드 탭의 오늘 소스와 동기화됩니다. 파일을 올리면 여기에도 바로 반영됩니다.",
    };
  }

  const counts = new Map<string, number>();
  for (const source of sources) {
    const label = sourceTypeLabel(source.originalType);
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }

  const breakdown = Array.from(counts.entries())
    .map(([label, count]) => `${count} ${label}`)
    .join(", ");

  return {
    description: `팟캐스트가 ${sources.length}개 문서(${breakdown}) 기반으로 생성됩니다.`,
  };
}

function sourceTypeLabel(contentType: string): string {
  if (contentType === "application/pdf") return "PDF";
  if (contentType === "image/png") return "PNG";
  if (contentType === "image/jpeg") return "JPG";
  if (contentType === "image/webp") return "WEBP";
  return "문서";
}

function formatRequestTime(value?: string): string {
  if (!value) return "기록 없음";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "기록 없음";

  const parts = new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  })
    .formatToParts(date)
    .reduce<Record<string, string>>((acc, part) => {
      if (part.type !== "literal") {
        acc[part.type] = part.value;
      }
      return acc;
    }, {});

  return `${parts.month}/${parts.day} ${parts.hour}시${parts.minute}분${parts.second}초`;
}
