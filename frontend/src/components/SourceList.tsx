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
      <div className="text-center py-8">
        <p className="text-[#b3b3b3] text-sm">업로드된 소스가 없습니다</p>
      </div>
    );
  }

  return (
    <ul className="space-y-2">
      {sources.map((source) => (
        <li
          key={source.sourceId}
          className="flex items-center justify-between bg-[#181818] rounded-lg px-4 py-3"
        >
          <div className="flex items-center gap-3 min-w-0">
            <FileTypeIcon type={source.originalType} />
            <div className="min-w-0">
              <p className="text-sm text-white truncate">{source.fileName}</p>
              <p className="text-xs text-[#535353]">
                {formatTime(source.uploadedAt)}
              </p>
            </div>
          </div>
          <div className="flex-shrink-0 ml-2">
            {confirmId === source.sourceId ? (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => {
                    onDelete(source.sourceId);
                    setConfirmId(null);
                  }}
                  disabled={deleting === source.sourceId}
                  className="text-xs text-red-400 hover:text-red-300 disabled:opacity-50"
                >
                  {deleting === source.sourceId ? "삭제 중..." : "확인"}
                </button>
                <button
                  onClick={() => setConfirmId(null)}
                  className="text-xs text-[#b3b3b3] hover:text-white"
                >
                  취소
                </button>
              </div>
            ) : (
              <button
                onClick={() => setConfirmId(source.sourceId)}
                className="text-[#b3b3b3] hover:text-red-400 transition-colors p-1"
                aria-label="삭제"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
