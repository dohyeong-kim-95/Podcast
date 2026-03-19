"use client";

import { useRef, useState } from "react";

const ACCEPTED_TYPES = [
  "application/pdf",
  "image/png",
  "image/jpeg",
  "image/webp",
];

interface UploadZoneProps {
  onUpload: (files: File[]) => void;
  uploading: boolean;
}

export default function UploadZone({ onUpload, uploading }: UploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const handleFiles = (fileList: FileList | null) => {
    if (!fileList) return;
    const valid = Array.from(fileList).filter((f) =>
      ACCEPTED_TYPES.includes(f.type)
    );
    if (valid.length > 0) {
      onUpload(valid);
    }
  };

  return (
    <div
      className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
        dragOver
          ? "border-[#1DB954] bg-[#1DB954]/10"
          : "border-[#535353] bg-[#181818]"
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
        onClick={() => inputRef.current?.click()}
        disabled={uploading}
        className="bg-[#1DB954] text-black font-semibold py-3 px-6 rounded-full hover:bg-[#1ed760] disabled:opacity-50 transition-colors"
      >
        {uploading ? "업로드 중..." : "파일 선택"}
      </button>
      <p className="text-[#b3b3b3] text-sm mt-3">
        PDF, PNG, JPG, WEBP (최대 20MB)
      </p>
      <p className="text-[#535353] text-xs mt-1">
        또는 파일을 여기에 드래그하세요
      </p>
    </div>
  );
}
