"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import ProtectedRoute from "@/components/ProtectedRoute";
import AudioPlayer from "@/components/AudioPlayer";
import FeedbackBar from "@/components/FeedbackBar";
import { useAuth } from "@/lib/auth-context";
import { getTodayPodcast, triggerGenerate, type Podcast } from "@/lib/api";

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
  const [loading, setLoading] = useState(true);
  const [retrying, setRetrying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPodcast = useCallback(async () => {
    try {
      setError(null);
      const res = await getTodayPodcast();
      setPodcast(res.podcast);
    } catch {
      setError("팟캐스트 정보를 불러올 수 없습니다");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPodcast();
  }, [fetchPodcast]);

  // Poll while generating
  useEffect(() => {
    if (!podcast) return;
    const status = podcast.status;
    if (!["generating", "pending", "retry_1", "retry_2"].includes(status)) return;

    const interval = setInterval(fetchPodcast, 5000);
    return () => clearInterval(interval);
  }, [podcast, fetchPodcast]);

  const handleRetry = useCallback(async () => {
    setRetrying(true);
    setError(null);
    try {
      await triggerGenerate();
      await fetchPodcast();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "재생성에 실패했습니다";
      if (msg.includes("409")) {
        setError("이미 생성 중입니다");
      } else {
        setError(msg);
      }
    } finally {
      setRetrying(false);
    }
  }, [fetchPodcast]);

  return (
    <div className="min-h-screen bg-[#121212] text-white">
      <header className="flex items-center justify-between px-4 py-3 border-b border-[#282828]">
        <h1 className="text-lg font-bold">Daily Podcast</h1>
        <button
          onClick={signOut}
          className="text-sm text-[#b3b3b3] hover:text-white transition-colors"
        >
          로그아웃
        </button>
      </header>

      <main className="px-4 py-6 space-y-4">
        <div className="mb-2">
          <p className="text-[#b3b3b3] text-sm">
            {user?.displayName || user?.email}님, 안녕하세요
          </p>
        </div>

        {error && (
          <div className="bg-red-900/30 border border-red-800 rounded-lg px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {loading ? (
          <LoadingState />
        ) : podcast?.status === "completed" && podcast.audioUrl ? (
          <CompletedState podcast={podcast} />
        ) : podcast && ["generating", "pending", "retry_1", "retry_2"].includes(podcast.status) ? (
          <GeneratingState />
        ) : podcast?.status === "failed" ? (
          <FailedState onRetry={handleRetry} retrying={retrying} />
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

function GeneratingState() {
  return (
    <div className="bg-[#181818] rounded-xl p-6 text-center">
      <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-[#282828] flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-[#1DB954] border-t-transparent rounded-full animate-spin" />
      </div>
      <p className="text-white text-sm font-medium">팟캐스트 생성 중...</p>
      <p className="text-[#535353] text-xs mt-1">
        잠시만 기다려주세요. 완료되면 자동으로 표시됩니다.
      </p>
    </div>
  );
}

function FailedState({ onRetry, retrying }: { onRetry: () => void; retrying: boolean }) {
  return (
    <div className="bg-[#181818] rounded-xl p-6 text-center">
      <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-[#282828] flex items-center justify-center">
        <svg className="w-6 h-6 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
        </svg>
      </div>
      <p className="text-white text-sm font-medium">팟캐스트 생성에 실패했습니다</p>
      <p className="text-[#535353] text-xs mt-1 mb-4">
        다시 시도해주세요
      </p>
      <button
        onClick={onRetry}
        disabled={retrying}
        className="px-6 py-2.5 bg-[#1DB954] text-black font-semibold rounded-full hover:bg-[#1ed760] transition-colors disabled:opacity-50"
      >
        {retrying ? (
          <span className="flex items-center gap-2">
            <div className="w-4 h-4 border-2 border-black border-t-transparent rounded-full animate-spin" />
            생성 중...
          </span>
        ) : (
          "다시 생성"
        )}
      </button>
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
      <p className="text-white text-sm font-medium">업로드된 소스가 없습니다</p>
      <p className="text-[#535353] text-xs mt-1">
        소스를 업로드하면 다음 날 아침 팟캐스트가 생성됩니다
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

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m === 0) return `${s}초`;
  if (s === 0) return `${m}분`;
  return `${m}분 ${s}초`;
}
