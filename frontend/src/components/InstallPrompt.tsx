"use client";

import { useEffect, useState } from "react";

interface DeferredInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
}

export default function InstallPrompt() {
  const [promptEvent, setPromptEvent] = useState<DeferredInstallPromptEvent | null>(null);
  const [installed, setInstalled] = useState(false);

  useEffect(() => {
    const handleBeforeInstallPrompt = (event: Event) => {
      event.preventDefault();
      setPromptEvent(event as DeferredInstallPromptEvent);
    };

    const handleInstalled = () => {
      setInstalled(true);
      setPromptEvent(null);
    };

    window.addEventListener("beforeinstallprompt", handleBeforeInstallPrompt);
    window.addEventListener("appinstalled", handleInstalled);

    return () => {
      window.removeEventListener("beforeinstallprompt", handleBeforeInstallPrompt);
      window.removeEventListener("appinstalled", handleInstalled);
    };
  }, []);

  if (!promptEvent || installed) {
    return null;
  }

  const handleInstall = async () => {
    await promptEvent.prompt();
    const choice = await promptEvent.userChoice;
    if (choice.outcome === "accepted") {
      setInstalled(true);
      setPromptEvent(null);
    }
  };

  return (
    <section className="rounded-2xl border border-[#2f5f45] bg-[linear-gradient(135deg,rgba(29,185,84,0.18),rgba(18,18,18,0.95))] p-4 shadow-[0_18px_60px_rgba(0,0,0,0.28)]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-white">앱처럼 설치</p>
          <p className="mt-1 text-xs leading-5 text-[#d3d3d3]">
            홈 화면에 추가하면 오프라인 화면과 알림 흐름을 더 안정적으로 사용할 수 있습니다.
          </p>
        </div>
        <button
          type="button"
          onClick={handleInstall}
          className="shrink-0 rounded-full bg-[#1DB954] px-4 py-2 text-sm font-semibold text-black transition-colors hover:bg-[#1ed760]"
        >
          설치
        </button>
      </div>
    </section>
  );
}
