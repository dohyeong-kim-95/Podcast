"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getSupabaseBrowserClient } from "@/lib/supabase";

export default function AuthCallbackPage() {
  const router = useRouter();

  useEffect(() => {
    let active = true;

    const completeAuth = async () => {
      const supabase = getSupabaseBrowserClient();
      const params = new URLSearchParams(window.location.search);
      const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ""));
      const code = params.get("code");
      const next = params.get("next") || "/";
      const accessToken = hashParams.get("access_token");
      const refreshToken = hashParams.get("refresh_token");

      if (code) {
        const { error } = await supabase.auth.exchangeCodeForSession(code);
        if (!active) {
          return;
        }

        if (error) {
          router.replace(`/login?error=${encodeURIComponent(error.message)}`);
          return;
        }

        router.replace(next);
        return;
      }

      if (accessToken && refreshToken) {
        const { error } = await supabase.auth.setSession({
          access_token: accessToken,
          refresh_token: refreshToken,
        });
        if (!active) {
          return;
        }

        if (error) {
          router.replace(`/login?error=${encodeURIComponent(error.message)}`);
          return;
        }

        router.replace(next);
        return;
      }

      const { data } = await supabase.auth.getSession();
      if (!active) {
        return;
      }

      if (data.session) {
        router.replace(next);
        return;
      }

      router.replace("/login");
    };

    void completeAuth();

    return () => {
      active = false;
    };
  }, [router]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#121212] text-white">
      <div className="flex flex-col items-center gap-4">
        <div className="w-8 h-8 border-2 border-[#1DB954] border-t-transparent rounded-full animate-spin" />
        <p className="text-sm text-[#b3b3b3]">로그인 세션을 확인하는 중...</p>
      </div>
    </div>
  );
}
