"use client";

import { useState } from "react";
import type { Source } from "@/lib/api";

interface SourceListProps {
  sources: Source[];
  onDelete: (sourceId: string) => void;
  deleting: string | null;
}

function FileTypeIcon({ type }: { type: string }) {
  if (type.startsWith("image/")) {
    return <span className="text-lg" role="img" aria-label="image">&#128444;</span>;
  }
  return <span className="text-lg" role="img" aria-label="document">&#128196;</span>;
}

function formatTime(isoString: string): string {
  try {
    const d = new Date(isoString);
    return d.toLocaleTimeString("ko-KR", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

export default function SourceList({ sources, onDelete, deleting }: SourceListProps) {
  const [confirmId, setConfirmId] = useState<string | null>(null);

  if (sources.length === 0) {
    return (
      <div className="rounded-2xl border border-[#242424] bg-[#171717] px-5 py-8 text-center">
        <p className="text-sm text-[#e2e2e2]">업로드된 소스가 없습니다</p>
        <p className="mt-2 text-xs text-[#7a7a7a]">PDF나 이미지를 올리면 다음 생성 윈도우에 자동으로 포함됩니다.</p>
      </div>
    );
  }

  return (
    <ul className="space-y-2.5">
      {sources.map((source) => (
        <li
          key={source.sourceId}
          className="flex items-center justify-between rounded-2xl border border-[#222222] bg-[#181818] px-4 py-3.5"
        >
          <div className="min-w-0 flex items-center gap-3">
            <FileTypeIcon type={source.originalType} />
            <div className="min-w-0">
              <p className="truncate text-sm text-white">{source.fileName}</p>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-[#6f6f6f]">
                <span>{formatTime(source.uploadedAt)}</span>
                <span className="rounded-full border border-[#2a2a2a] px-2 py-0.5 text-[10px] uppercase tracking-[0.16em] text-[#9a9a9a]">
                  {source.originalType.startsWith("image/") ? "image" : "pdf"}
                </span>
                {source.convertedType === "application/pdf" && (
                  <span className="rounded-full border border-[#1DB954]/25 px-2 py-0.5 text-[10px] uppercase tracking-[0.16em] text-[#89d8a5]">
                    converted
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="ml-2 flex-shrink-0">
            {confirmId === source.sourceId ? (
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    onDelete(source.sourceId);
                    setConfirmId(null);
                  }}
                  disabled={deleting === source.sourceId}
                  className="min-h-10 rounded-full bg-red-950/40 px-3 text-xs font-semibold text-red-300 transition-colors hover:bg-red-950/60 disabled:opacity-50"
                >
                  {deleting === source.sourceId ? "삭제 중..." : "삭제 확인"}
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmId(null)}
                  className="min-h-10 rounded-full px-3 text-xs font-semibold text-[#b3b3b3] transition-colors hover:bg-white/5 hover:text-white"
                >
                  취소
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setConfirmId(source.sourceId)}
                className="rounded-full p-2.5 text-[#b3b3b3] transition-colors hover:bg-red-950/20 hover:text-red-300"
                aria-label={`${source.fileName} 삭제`}
              >
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
