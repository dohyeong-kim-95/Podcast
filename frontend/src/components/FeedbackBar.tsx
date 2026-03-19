"use client";

import { useState, useCallback } from "react";
import { submitFeedback } from "@/lib/api";

interface FeedbackBarProps {
  podcastId: string;
  currentFeedback?: string | null;
}

const RATINGS = [
  { value: "good", label: "좋았어요", icon: "👍" },
  { value: "normal", label: "보통", icon: "🤷" },
  { value: "bad", label: "별로예요", icon: "👎" },
] as const;

export default function FeedbackBar({ podcastId, currentFeedback }: FeedbackBarProps) {
  const [selected, setSelected] = useState<string | null>(currentFeedback || null);
  const [submitting, setSubmitting] = useState(false);

  const handleSelect = useCallback(async (rating: string) => {
    if (submitting || selected === rating) return;

    setSubmitting(true);
    setSelected(rating);
    try {
      await submitFeedback(podcastId, rating);
    } catch {
      setSelected(currentFeedback || null);
    } finally {
      setSubmitting(false);
    }
  }, [podcastId, submitting, selected, currentFeedback]);

  return (
    <div className="bg-[#181818] rounded-xl p-4">
      <p className="text-sm text-[#b3b3b3] mb-3">오늘의 팟캐스트는 어땠나요?</p>
      <div className="flex gap-2">
        {RATINGS.map(({ value, label, icon }) => (
          <button
            key={value}
            onClick={() => handleSelect(value)}
            disabled={submitting}
            className={`flex-1 flex flex-col items-center gap-1 py-2.5 rounded-lg transition-colors ${
              selected === value
                ? "bg-[#1DB954] text-black"
                : "bg-[#282828] text-[#b3b3b3] hover:bg-[#333333] hover:text-white"
            }`}
          >
            <span className="text-lg">{icon}</span>
            <span className="text-xs font-medium">{label}</span>
          </button>
        ))}
      </div>
      {selected && (
        <p className="text-xs text-[#1DB954] mt-2 text-center">
          피드백이 반영되었습니다
        </p>
      )}
    </div>
  );
}
