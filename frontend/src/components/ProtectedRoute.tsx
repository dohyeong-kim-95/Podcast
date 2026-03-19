"use client";

import { useAuth } from "@/lib/auth-context";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function ProtectedRoute({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, loading, verified } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [user, loading, router]);

  if (loading || verified === "pending") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#121212]">
        <div className="w-8 h-8 border-2 border-[#1DB954] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!user) {
    return null;
  }

  if (verified === "denied") {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-[#121212] px-6">
        <div className="w-full max-w-sm flex flex-col items-center gap-4 text-center">
          <div className="w-12 h-12 rounded-full bg-red-900/30 flex items-center justify-center">
            <svg className="w-6 h-6 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
            </svg>
          </div>
          <h2 className="text-lg font-bold text-white">접근이 거부되었습니다</h2>
          <p className="text-sm text-[#b3b3b3]">
            허용된 이메일 목록에 포함되어 있지 않습니다. 관리자에게 문의하세요.
          </p>
        </div>
      </div>
    );
  }

  if (verified !== "verified") {
    return null;
  }

  return <>{children}</>;
}
