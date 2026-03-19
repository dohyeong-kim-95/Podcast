"use client";

import { useRef, useState, useEffect, useCallback } from "react";
import { markDownloaded } from "@/lib/api";

interface AudioPlayerProps {
  audioUrl: string;
  podcastId: string;
  durationSeconds?: number;
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

const SPEED_OPTIONS = [1, 1.5, 2] as const;

export default function AudioPlayer({ audioUrl, podcastId, durationSeconds }: AudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const progressRef = useRef<HTMLDivElement>(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(durationSeconds || 0);
  const [speedIndex, setSpeedIndex] = useState(0);
  const [isDragging, setIsDragging] = useState(false);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const onLoadedMetadata = () => {
      if (audio.duration && isFinite(audio.duration)) {
        setDuration(audio.duration);
      }
    };
    const onTimeUpdate = () => {
      if (!isDragging) {
        setCurrentTime(audio.currentTime);
      }
    };
    const onEnded = () => setIsPlaying(false);

    audio.addEventListener("loadedmetadata", onLoadedMetadata);
    audio.addEventListener("timeupdate", onTimeUpdate);
    audio.addEventListener("ended", onEnded);

    return () => {
      audio.removeEventListener("loadedmetadata", onLoadedMetadata);
      audio.removeEventListener("timeupdate", onTimeUpdate);
      audio.removeEventListener("ended", onEnded);
    };
  }, [isDragging]);

  const togglePlay = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;

    if (isPlaying) {
      audio.pause();
    } else {
      audio.play();
    }
    setIsPlaying(!isPlaying);
  }, [isPlaying]);

  const cycleSpeed = useCallback(() => {
    const nextIndex = (speedIndex + 1) % SPEED_OPTIONS.length;
    setSpeedIndex(nextIndex);
    if (audioRef.current) {
      audioRef.current.playbackRate = SPEED_OPTIONS[nextIndex];
    }
  }, [speedIndex]);

  const seekTo = useCallback((clientX: number) => {
    const bar = progressRef.current;
    const audio = audioRef.current;
    if (!bar || !audio || !duration) return;

    const rect = bar.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    const newTime = ratio * duration;
    audio.currentTime = newTime;
    setCurrentTime(newTime);
  }, [duration]);

  const handleProgressClick = useCallback((e: React.MouseEvent) => {
    seekTo(e.clientX);
  }, [seekTo]);

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    setIsDragging(true);
    seekTo(e.touches[0].clientX);
  }, [seekTo]);

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    if (isDragging) {
      seekTo(e.touches[0].clientX);
    }
  }, [isDragging, seekTo]);

  const handleTouchEnd = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    setIsDragging(true);
    seekTo(e.clientX);

    const onMouseMove = (ev: MouseEvent) => seekTo(ev.clientX);
    const onMouseUp = () => {
      setIsDragging(false);
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  }, [seekTo]);

  const handleDownload = useCallback(async () => {
    const link = document.createElement("a");
    link.href = audioUrl;
    link.download = `podcast-${podcastId}.mp3`;
    link.click();

    try {
      await markDownloaded(podcastId);
    } catch {
      // Best effort - don't block UX
    }
  }, [audioUrl, podcastId]);

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

  return (
    <div className="bg-[#181818] rounded-xl p-4">
      <audio ref={audioRef} src={audioUrl} preload="metadata" />

      {/* Controls row */}
      <div className="flex items-center gap-3 mb-3">
        {/* Play/Pause */}
        <button
          onClick={togglePlay}
          className="w-12 h-12 flex-shrink-0 rounded-full bg-[#1DB954] flex items-center justify-center hover:bg-[#1ed760] transition-colors"
          aria-label={isPlaying ? "일시정지" : "재생"}
        >
          {isPlaying ? (
            <svg className="w-5 h-5 text-black" fill="currentColor" viewBox="0 0 24 24">
              <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" />
            </svg>
          ) : (
            <svg className="w-5 h-5 text-black ml-0.5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M8 5v14l11-7z" />
            </svg>
          )}
        </button>

        {/* Time + progress */}
        <div className="flex-1 min-w-0">
          <div
            ref={progressRef}
            className="relative h-2 bg-[#535353] rounded-full cursor-pointer group"
            onClick={handleProgressClick}
            onMouseDown={handleMouseDown}
            onTouchStart={handleTouchStart}
            onTouchMove={handleTouchMove}
            onTouchEnd={handleTouchEnd}
          >
            <div
              className="absolute left-0 top-0 h-full bg-[#1DB954] rounded-full transition-[width] duration-100"
              style={{ width: `${progress}%` }}
            />
            <div
              className="absolute top-1/2 -translate-y-1/2 w-3 h-3 bg-white rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
              style={{ left: `calc(${progress}% - 6px)` }}
            />
          </div>
          <div className="flex justify-between mt-1">
            <span className="text-[10px] text-[#b3b3b3]">{formatTime(currentTime)}</span>
            <span className="text-[10px] text-[#b3b3b3]">{formatTime(duration)}</span>
          </div>
        </div>
      </div>

      {/* Speed + Download row */}
      <div className="flex items-center justify-between">
        <button
          onClick={cycleSpeed}
          className="px-3 py-1 text-xs font-semibold text-[#b3b3b3] border border-[#535353] rounded-full hover:text-white hover:border-white transition-colors"
        >
          {SPEED_OPTIONS[speedIndex]}x
        </button>

        <button
          onClick={handleDownload}
          className="flex items-center gap-1.5 px-3 py-1 text-xs text-[#b3b3b3] hover:text-white transition-colors"
          aria-label="다운로드"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          다운로드
        </button>
      </div>
    </div>
  );
}
