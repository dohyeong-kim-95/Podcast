"use client";

import Link from "next/link";

export default function OfflinePage() {
  return (
    <main className="min-h-screen bg-[#121212] px-6 py-12 text-white">
      <div className="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center rounded-3xl border border-[#282828] bg-[#181818] p-6 shadow-[0_24px_80px_rgba(0,0,0,0.4)]">
        <div className="mb-6 flex h-14 w-14 items-center justify-center rounded-2xl bg-[#1DB954]/15 text-[#1DB954]">
          <svg className="h-7 w-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M8.111 16.404a5 5 0 117.778 0M5.636 13.93a8.5 8.5 0 0112.728 0M3 11.293a12 12 0 0118 0M12 20h.01" />
          </svg>
        </div>
        <p className="text-2xl font-bold">오프라인 상태입니다</p>
        <p className="mt-3 text-sm leading-6 text-[#b3b3b3]">
          네트워크가 복구되면 홈으로 돌아가 최신 팟캐스트와 설정을 다시 불러올 수 있습니다.
        </p>
        <div className="mt-8 space-y-3">
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="w-full rounded-full bg-[#1DB954] py-3 text-sm font-semibold text-black transition-colors hover:bg-[#1ed760]"
          >
            다시 시도
          </button>
          <Link
            href="/"
            className="flex w-full items-center justify-center rounded-full border border-[#2a2a2a] py-3 text-sm font-semibold text-white transition-colors hover:border-[#1DB954]"
          >
            홈으로 이동
          </Link>
        </div>
      </div>
    </main>
  );
}
