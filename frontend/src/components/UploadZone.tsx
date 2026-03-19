"use client";

import { useRef, useState } from "react";

const ACCEPTED_TYPES = [
  "application/pdf",
  "image/png",
  "image/jpeg",
  "image/webp",
];

interface UploadZoneProps {
  onUpload: (files: File[], rejectedFiles: File[]) => void;
  uploading: boolean;
}

export default function UploadZone({ onUpload, uploading }: UploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const handleFiles = (fileList: FileList | null) => {
    if (!fileList) return;
    const files = Array.from(fileList);
    const valid = files.filter((file) => ACCEPTED_TYPES.includes(file.type));
    const rejected = files.filter((file) => !ACCEPTED_TYPES.includes(file.type));
    onUpload(valid, rejected);
  };

  return (
    <div
      className={`rounded-xl border-2 border-dashed p-8 text-center transition-colors ${
        dragOver
          ? "border-[#1DB954] bg-[#1DB954]/10"
          : "border-[#2f2f2f] bg-[#181818]"
      }`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        handleFiles(e.dataTransfer.files);
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.png,.jpg,.jpeg,.webp"
        multiple
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={uploading}
        className="min-h-12 rounded-full bg-[#1DB954] px-6 py-3 font-semibold text-black transition-colors hover:bg-[#1ed760] disabled:opacity-50"
      >
        {uploading ? "업로드 중..." : "파일 선택"}
      </button>
      <p className="mt-3 text-sm text-[#b3b3b3]">
        PDF, PNG, JPG, WEBP (최대 20MB)
      </p>
      <p className="mt-1 text-xs text-[#7a7a7a]">
        파일을 드래그하거나 여러 개를 한 번에 선택할 수 있습니다.
      </p>
    </div>
  );
}
