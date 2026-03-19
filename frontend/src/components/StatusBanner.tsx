"use client";

import Link from "next/link";
import type { NbSessionStatusResponse } from "@/lib/api";

export default function StatusBanner({
  session,
}: {
  session: NbSessionStatusResponse | null;
}) {
  if (!session) {
    return null;
  }

  const authPending = session.authSession?.status === "pending";

  if (!authPending && !["expired", "expiring_soon", "missing"].includes(session.status)) {
    return null;
  }

  const config = authPending
    ? {
        title: "재인증 진행 중",
        description: "열린 탭에서 NotebookLM 로그인을 완료하면 상태가 자동으로 갱신됩니다.",
        className: "bg-sky-950/30 border-sky-800/50 text-sky-200",
        linkLabel: "세션 상태 보기",
      }
    : session.status === "expiring_soon"
      ? {
          title: "NotebookLM 세션이 곧 만료됩니다",
          description: buildExpiryMessage(session.expiresAt, "지금 재인증해 두면 생성 실패를 줄일 수 있습니다."),
          className: "bg-amber-950/30 border-amber-800/50 text-amber-200",
          linkLabel: "지금 재인증",
        }
      : {
          title: "NotebookLM 세션 재인증이 필요합니다",
          description:
            session.status === "missing"
              ? "아직 연결된 세션이 없습니다. 새 탭에서 로그인해 세션을 저장하세요."
              : buildExpiryMessage(session.expiresAt, "세션이 만료되어 다음 생성 전에 다시 로그인해야 합니다."),
          className: "bg-red-950/30 border-red-800/50 text-red-200",
          linkLabel: "세션 관리",
        };

  return (
    <div className={`rounded-xl border px-4 py-3 ${config.className}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold">{config.title}</p>
          <p className="mt-1 text-xs leading-5 opacity-90">{config.description}</p>
        </div>
        <Link
          href="/settings"
          className="shrink-0 rounded-full border border-white/15 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-white/10"
        >
          {config.linkLabel}
        </Link>
      </div>
    </div>
  );
}

function buildExpiryMessage(expiresAt: string | null | undefined, fallback: string): string {
  if (!expiresAt) {
    return fallback;
  }

  const formatted = new Date(expiresAt).toLocaleString("ko-KR", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  return `${fallback} 예정 만료 시각: ${formatted}`;
}
