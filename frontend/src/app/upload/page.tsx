"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import ProtectedRoute from "@/components/ProtectedRoute";
import UploadZone from "@/components/UploadZone";
import SourceList from "@/components/SourceList";
import { uploadSource, listSources, deleteSource, type Source } from "@/lib/api";

export default function UploadPage() {
  return (
    <ProtectedRoute>
      <UploadContent />
    </ProtectedRoute>
  );
}

function UploadContent() {
  const router = useRouter();
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState<{ done: number; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchSources = useCallback(async () => {
    try {
      const result = await listSources();
      setSources(result.sources);
    } catch {
      // Silently fail — list may be empty
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSources();
  }, [fetchSources]);

  const handleUpload = async (files: File[]) => {
    setUploading(true);
    setError(null);
    setUploadProgress({ done: 0, total: files.length });

    for (let i = 0; i < files.length; i++) {
      try {
        const result = await uploadSource(files[i]);
        setSources((prev) => [...prev, result]);
        setUploadProgress({ done: i + 1, total: files.length });
      } catch {
        setError(`${files[i].name} 업로드 실패`);
      }
    }

    setUploading(false);
    setUploadProgress(null);
  };

  const handleDelete = async (sourceId: string) => {
    setDeleting(sourceId);
    try {
      await deleteSource(sourceId);
      setSources((prev) => prev.filter((s) => s.sourceId !== sourceId));
    } catch {
      setError("삭제에 실패했습니다");
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div className="min-h-screen bg-[#121212] text-white">
      <header className="flex items-center px-4 py-3 border-b border-[#282828]">
        <button
          onClick={() => router.push("/")}
          className="text-[#b3b3b3] hover:text-white mr-3 transition-colors"
          aria-label="뒤로"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <h1 className="text-lg font-bold">소스 업로드</h1>
      </header>

      <main className="px-4 py-6 max-w-lg mx-auto space-y-6">
        <UploadZone onUpload={handleUpload} uploading={uploading} />

        {uploadProgress && (
          <div className="bg-[#181818] rounded-lg px-4 py-3">
            <div className="flex justify-between text-sm text-[#b3b3b3] mb-2">
              <span>업로드 중</span>
              <span>{uploadProgress.done}/{uploadProgress.total}</span>
            </div>
            <div className="w-full bg-[#282828] rounded-full h-1.5">
              <div
                className="bg-[#1DB954] h-1.5 rounded-full transition-all"
                style={{
                  width: `${(uploadProgress.done / uploadProgress.total) * 100}%`,
                }}
              />
            </div>
          </div>
        )}

        {error && (
          <div className="bg-red-900/20 border border-red-800/30 rounded-lg px-4 py-3">
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}

        <div>
          <h2 className="text-sm font-semibold text-[#b3b3b3] mb-3">
            오늘의 소스 ({sources.length})
          </h2>
          {loading ? (
            <div className="flex justify-center py-8">
              <div className="w-6 h-6 border-2 border-[#1DB954] border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <SourceList
              sources={sources}
              onDelete={handleDelete}
              deleting={deleting}
            />
          )}
        </div>
      </main>
    </div>
  );
}
