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
  const [uploadProgress, setUploadProgress] = useState<{
    processedBytes: number;
    totalBytes: number;
    completed: number;
    total: number;
    currentFile: string | null;
  } | null>(null);
  const [errors, setErrors] = useState<string[]>([]);

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

  const handleUpload = async (files: File[], rejectedFiles: File[]) => {
    const nextErrors = rejectedFiles.map((file) => `${file.name}: 허용되지 않은 파일 형식입니다`);
    setErrors(nextErrors);

    if (files.length === 0) {
      return;
    }

    setUploading(true);
    const totalBytes = files.reduce((sum, file) => sum + file.size, 0);
    let processedBytes = 0;

    setUploadProgress({
      processedBytes: 0,
      totalBytes,
      completed: 0,
      total: files.length,
      currentFile: files[0]?.name ?? null,
    });

    for (let i = 0; i < files.length; i++) {
      let uploadedBytes = 0;
      let uploadSucceeded = false;

      try {
        const result = await uploadSource(files[i], (currentUploadedBytes) => {
          uploadedBytes = Math.min(files[i].size, currentUploadedBytes);
          setUploadProgress({
            processedBytes: processedBytes + uploadedBytes,
            totalBytes,
            completed: i,
            total: files.length,
            currentFile: files[i].name,
          });
        });
        uploadSucceeded = true;
        uploadedBytes = files[i].size;
        setSources((prev) => [...prev, result]);
      } catch {
        nextErrors.push(`${files[i].name}: 업로드 실패`);
      } finally {
        processedBytes += uploadSucceeded ? files[i].size : uploadedBytes;
        setUploadProgress({
          processedBytes,
          totalBytes,
            completed: i + 1,
            total: files.length,
            currentFile: files[i + 1]?.name ?? null,
        });
      }
    }

    setUploading(false);
    setUploadProgress(null);
    setErrors(nextErrors);
  };

  const handleDelete = async (sourceId: string) => {
    setDeleting(sourceId);
    try {
      await deleteSource(sourceId);
      setSources((prev) => prev.filter((s) => s.sourceId !== sourceId));
    } catch {
      setErrors((current) => [...current, "삭제에 실패했습니다"]);
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div className="min-h-screen bg-[#121212] text-white">
      <header className="sticky top-0 z-10 border-b border-[#282828] bg-[#121212]/95 px-4 py-3 backdrop-blur">
        <button
          onClick={() => router.push("/")}
          type="button"
          className="mr-3 rounded-full p-2 text-[#b3b3b3] transition-colors hover:bg-white/5 hover:text-white"
          aria-label="뒤로"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <h1 className="text-lg font-bold">소스 업로드</h1>
      </header>

      <main className="mx-auto max-w-lg space-y-6 px-4 py-6">
        <section className="rounded-[1.5rem] border border-[#242424] bg-[#171717] p-5 shadow-[0_20px_60px_rgba(0,0,0,0.28)]">
          <div className="mb-4">
            <p className="text-sm font-semibold text-white">오늘의 소스 모으기</p>
            <p className="mt-1 text-xs leading-5 text-[#8d8d8d]">
              PDF 또는 이미지를 여러 개 올릴 수 있습니다. 업로드된 항목은 다음 생성 윈도우에 자동으로 포함됩니다.
            </p>
          </div>
          <UploadZone onUpload={handleUpload} uploading={uploading} />
        </section>

        {uploadProgress && (
          <div className="rounded-2xl border border-[#2a2a2a] bg-[#181818] px-4 py-4">
            <div className="mb-2 flex items-center justify-between text-sm text-[#cfcfcf]">
              <span>업로드 중</span>
              <span>{uploadProgress.completed}/{uploadProgress.total}</span>
            </div>
            <div className="mb-2 h-2 w-full rounded-full bg-[#282828]">
              <div
                className="h-2 rounded-full bg-[#1DB954] transition-all"
                style={{
                  width: `${uploadProgress.totalBytes === 0 ? 0 : (uploadProgress.processedBytes / uploadProgress.totalBytes) * 100}%`,
                }}
              />
            </div>
            <div className="flex items-center justify-between text-xs text-[#8d8d8d]">
              <span>
                {formatBytes(uploadProgress.processedBytes)} / {formatBytes(uploadProgress.totalBytes)}
              </span>
              <span>{uploadProgress.currentFile ? `다음: ${uploadProgress.currentFile}` : "마무리 중..."}</span>
            </div>
          </div>
        )}

        {errors.length > 0 && (
          <div className="rounded-2xl border border-red-800/30 bg-red-950/20 px-4 py-3">
            <p className="mb-2 text-sm font-semibold text-red-200">확인이 필요한 항목</p>
            <ul className="space-y-1 text-sm text-red-300">
              {errors.map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          </div>
        )}

        <div>
          <h2 className="mb-3 text-sm font-semibold text-[#b3b3b3]">
            오늘의 소스 ({sources.length})
          </h2>
          {loading ? (
            <div className="rounded-2xl border border-[#242424] bg-[#171717] py-10">
              <div className="flex justify-center">
                <div className="h-6 w-6 rounded-full border-2 border-[#1DB954] border-t-transparent animate-spin" />
              </div>
              <p className="mt-3 text-center text-sm text-[#8d8d8d]">업로드된 소스를 불러오는 중...</p>
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

function formatBytes(value: number) {
  if (value < 1024 * 1024) {
    return `${Math.max(1, Math.round(value / 1024))}KB`;
  }

  return `${(value / (1024 * 1024)).toFixed(1)}MB`;
}
