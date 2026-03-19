import type { Metadata, Viewport } from "next";
import "./globals.css";
import BottomNav from "@/components/BottomNav";
import { AuthProvider } from "@/lib/auth-context";
import PwaRegistrar from "@/components/PwaRegistrar";

export const metadata: Metadata = {
  title: "Daily Podcast",
  description: "AI가 만드는 나만의 데일리 팟캐스트",
  manifest: "/manifest.json",
};

export const viewport: Viewport = {
  themeColor: "#121212",
  colorScheme: "dark",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body>
        <AuthProvider>
          {children}
          <BottomNav />
          <PwaRegistrar />
        </AuthProvider>
      </body>
    </html>
  );
}
