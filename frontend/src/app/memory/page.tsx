"use client";

import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import ProtectedRoute from "@/components/ProtectedRoute";
import { getMemory, updateMemory, type MemoryUpdate } from "@/lib/api";

const EMPTY_FORM: MemoryUpdate = {
  interests: "",
  tone: "",
  depth: "",
  custom: "",
};

export default function MemoryPage() {
  return (
    <ProtectedRoute>
      <MemoryContent />
    </ProtectedRoute>
  );
}

function MemoryContent() {
  const router = useRouter();
  const [form, setForm] = useState<MemoryUpdate>(EMPTY_FORM);
  const [initialForm, setInitialForm] = useState<MemoryUpdate>(EMPTY_FORM);
  const [feedbackCount, setFeedbackCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadMemory() {
      try {
        const memory = await getMemory();
        if (cancelled) return;

        const nextForm = {
          interests: memory.interests ?? "",
          tone: memory.tone ?? "",
          depth: memory.depth ?? "",
          custom: memory.custom ?? "",
        };

        setForm(nextForm);
        setInitialForm(nextForm);
        setFeedbackCount(memory.feedbackHistory.length);
        setError(null);
      } catch {
        if (!cancelled) {
          setError("메모리 정보를 불러오지 못했습니다");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadMemory();

    return () => {
      cancelled = true;
    };
  }, []);

  const isDirty = useMemo(
    () =>
      form.interests !== initialForm.interests ||
      form.tone !== initialForm.tone ||
      form.depth !== initialForm.depth ||
      form.custom !== initialForm.custom,
    [form, initialForm],
  );

  const handleChange =
    (field: keyof MemoryUpdate) =>
    (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      const value = event.target.value;
      setForm((current) => ({ ...current, [field]: value }));
      setSaved(false);
    };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (saving || !isDirty) return;

    setSaving(true);
    setError(null);
    setSaved(false);

    try {
      const memory = await updateMemory(form);
      const nextForm = {
        interests: memory.interests ?? "",
        tone: memory.tone ?? "",
        depth: memory.depth ?? "",
        custom: memory.custom ?? "",
      };
      setForm(nextForm);
      setInitialForm(nextForm);
      setFeedbackCount(memory.feedbackHistory.length);
      setSaved(true);
    } catch {
      setError("저장에 실패했습니다");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#121212] text-white">
      <header className="flex items-center px-4 py-3 border-b border-[#282828]">
        <button
          onClick={() => router.push("/")}
          className="text-[#b3b3b3] hover:text-white mr-3 transition-colors"
          aria-label="뒤로"
          type="button"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div>
          <h1 className="text-lg font-bold">메모리 설정</h1>
          <p className="text-xs text-[#b3b3b3]">생성 프롬프트에 반영되는 개인 설정</p>
        </div>
      </header>

      <main className="px-4 py-6 max-w-lg mx-auto">
        {loading ? (
          <div className="bg-[#181818] rounded-xl p-6 text-center">
            <div className="w-8 h-8 mx-auto mb-3 border-2 border-[#1DB954] border-t-transparent rounded-full animate-spin" />
            <p className="text-sm text-[#b3b3b3]">메모리를 불러오는 중...</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <section className="bg-[#181818] rounded-xl p-4 space-y-1">
              <p className="text-sm font-semibold">팟캐스트 취향</p>
              <p className="text-xs text-[#b3b3b3]">
                관심사와 원하는 설명 스타일을 적어두면 다음 생성부터 반영됩니다.
              </p>
              {feedbackCount > 0 && (
                <p className="text-xs text-[#1DB954] pt-1">
                  최근 피드백 {feedbackCount}건도 함께 참고됩니다.
                </p>
              )}
            </section>

            <Field
              label="관심 분야"
              hint="예: AI, 반도체, 거시경제"
              value={form.interests}
              onChange={handleChange("interests")}
            />

            <Field
              label="선호 톤"
              hint="예: 친근하지만 기술적으로 정확하게"
              value={form.tone}
              onChange={handleChange("tone")}
            />

            <Field
              label="깊이 수준"
              hint="예: 입문자용, 실무자 관점, 전문가 수준"
              value={form.depth}
              onChange={handleChange("depth")}
            />

            <Field
              label="추가 요청"
              hint="예: 핵심 요약 먼저, 용어 설명 포함"
              value={form.custom}
              onChange={handleChange("custom")}
              multiline
            />

            {error && (
              <div className="bg-red-900/20 border border-red-800/30 rounded-lg px-4 py-3">
                <p className="text-sm text-red-400">{error}</p>
              </div>
            )}

            {saved && (
              <div className="bg-[#1DB954]/15 border border-[#1DB954]/30 rounded-lg px-4 py-3">
                <p className="text-sm text-[#1DB954]">메모리를 저장했습니다</p>
              </div>
            )}

            <button
              type="submit"
              disabled={saving || !isDirty}
              className="w-full bg-[#1DB954] text-black font-semibold py-3 rounded-full hover:bg-[#1ed760] transition-colors disabled:opacity-50 disabled:hover:bg-[#1DB954]"
            >
              {saving ? "저장 중..." : "저장"}
            </button>
          </form>
        )}
      </main>
    </div>
  );
}

function Field({
  label,
  hint,
  value,
  onChange,
  multiline = false,
}: {
  label: string;
  hint: string;
  value: string;
  onChange: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => void;
  multiline?: boolean;
}) {
  return (
    <label className="block bg-[#181818] rounded-xl p-4">
      <span className="block text-sm font-semibold mb-1">{label}</span>
      <span className="block text-xs text-[#b3b3b3] mb-3">{hint}</span>
      {multiline ? (
        <textarea
          value={value}
          onChange={onChange}
          rows={5}
          className="w-full bg-[#121212] border border-[#282828] rounded-lg px-3 py-3 text-sm text-white placeholder:text-[#535353] focus:outline-none focus:ring-2 focus:ring-[#1DB954] resize-none"
          placeholder={hint}
        />
      ) : (
        <input
          type="text"
          value={value}
          onChange={onChange}
          className="w-full bg-[#121212] border border-[#282828] rounded-lg px-3 py-3 text-sm text-white placeholder:text-[#535353] focus:outline-none focus:ring-2 focus:ring-[#1DB954]"
          placeholder={hint}
        />
      )}
    </label>
  );
}
