"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  {
    href: "/",
    label: "홈",
    icon: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.8}
        d="M3 10.5L12 3l9 7.5M5.25 9.75V20.25h13.5V9.75"
      />
    ),
  },
  {
    href: "/upload",
    label: "업로드",
    icon: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.8}
        d="M12 16.5V6m0 0L8.25 9.75M12 6l3.75 3.75M4.5 18.75h15"
      />
    ),
  },
  {
    href: "/memory",
    label: "메모리",
    icon: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.8}
        d="M9.75 9.75h4.5m-4.5 4.5h3m-5.25 6h8.75A2.25 2.25 0 0018.5 18V6A2.25 2.25 0 0016.25 3.75H7.75A2.25 2.25 0 005.5 6v12A2.25 2.25 0 007.75 20.25z"
      />
    ),
  },
  {
    href: "/settings",
    label: "설정",
    icon: (
      <>
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.8}
          d="M10.5 6.75a1.5 1.5 0 113 0 1.5 1.5 0 01-3 0zm0 10.5a1.5 1.5 0 113 0 1.5 1.5 0 01-3 0zM4.5 12a1.5 1.5 0 113 0 1.5 1.5 0 01-3 0zm10.5 0a1.5 1.5 0 113 0 1.5 1.5 0 01-3 0z"
        />
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.8}
          d="M12 8.25v7.5M8.25 12h7.5"
        />
      </>
    ),
  },
] as const;

const HIDDEN_PATHS = new Set(["/login", "/offline"]);

export default function BottomNav() {
  const pathname = usePathname();

  if (!pathname || HIDDEN_PATHS.has(pathname)) {
    return null;
  }

  return (
    <>
      <div aria-hidden className="h-24" />
      <nav className="fixed inset-x-0 bottom-0 z-40 mx-auto max-w-xl px-4 pb-[calc(env(safe-area-inset-bottom)+1rem)]">
        <div className="rounded-[1.75rem] border border-white/10 bg-[rgba(16,16,16,0.92)] px-2 py-2 shadow-[0_-12px_40px_rgba(0,0,0,0.42)] backdrop-blur">
          <ul className="grid grid-cols-4 gap-1">
            {ITEMS.map((item) => {
              const active = pathname === item.href;

              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={`flex min-h-14 flex-col items-center justify-center rounded-2xl px-2 text-[11px] font-semibold transition-colors ${
                      active
                        ? "bg-[#1DB954] text-black"
                        : "text-[#9b9b9b] hover:bg-white/5 hover:text-white"
                    }`}
                  >
                    <svg className="mb-1 h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      {item.icon}
                    </svg>
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      </nav>
    </>
  );
}
