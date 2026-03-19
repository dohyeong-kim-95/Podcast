"use client";

import ProtectedRoute from "@/components/ProtectedRoute";
import { useAuth } from "@/lib/auth-context";

export default function Home() {
  return (
    <ProtectedRoute>
      <MainContent />
    </ProtectedRoute>
  );
}

function MainContent() {
  const { user, signOut } = useAuth();

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

      <main className="px-4 py-6">
        <div className="mb-6">
          <p className="text-[#b3b3b3] text-sm">
            {user?.displayName || user?.email}님, 안녕하세요
          </p>
        </div>

        <div className="bg-[#181818] rounded-xl p-6 text-center">
          <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-[#282828] flex items-center justify-center">
            <svg
              className="w-6 h-6 text-[#b3b3b3]"
              fill="currentColor"
              viewBox="0 0 24 24"
            >
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
      </main>
    </div>
  );
}
