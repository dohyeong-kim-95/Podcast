"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  type AuthChangeEvent,
  type Session,
  type User,
} from "@supabase/supabase-js";
import { getSupabaseBrowserClient } from "./supabase";

export interface AppUser {
  id: string;
  email: string | null;
  displayName: string | null;
}

interface AuthContextType {
  user: AppUser | null;
  loading: boolean;
  verified: "idle" | "pending" | "verified" | "denied";
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  verified: "idle",
  signInWithGoogle: async () => {},
  signOut: async () => {},
});

const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_BASE ||
  "http://localhost:8080"
).replace(/\/+$/, "");

const AUTH_VERIFY_TIMEOUT_MS = 10000;

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AppUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [verified, setVerified] = useState<"idle" | "pending" | "verified" | "denied">("idle");

  const mapUser = (value: User | null): AppUser | null => {
    if (!value) {
      return null;
    }

    return {
      id: value.id,
      email: value.email ?? null,
      displayName:
        value.user_metadata?.full_name ??
        value.user_metadata?.name ??
        value.user_metadata?.user_name ??
        null,
    };
  };

  useEffect(() => {
    const supabase = getSupabaseBrowserClient();

    const applySession = (session: Session | null) => {
      setUser(mapUser(session?.user ?? null));
      setLoading(false);
      if (!session?.user) {
        setVerified("idle");
      }
    };

    supabase.auth.getSession()
      .then(({ data }) => {
        applySession(data.session);
      })
      .catch(() => {
        setLoading(false);
      });

    const { data } = supabase.auth.onAuthStateChange(
      (_event: AuthChangeEvent, session: Session | null) => {
        applySession(session);
      },
    );

    return () => {
      data.subscription.unsubscribe();
    };
  }, []);

  // Verify with backend when user signs in
  useEffect(() => {
    if (!user) return;
    if (verified === "verified" || verified === "pending") return;

    let cancelled = false;
    const verifyWithBackend = async () => {
      setVerified("pending");
      try {
        const { data } = await getSupabaseBrowserClient().auth.getSession();
        const token = data.session?.access_token;
        if (!token) {
          if (!cancelled) {
            setVerified("idle");
          }
          return;
        }

        const controller = new AbortController();
        const timeoutId = window.setTimeout(() => controller.abort(), AUTH_VERIFY_TIMEOUT_MS);
        const res = await fetch(`${API_BASE}/api/auth/verify`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });
        window.clearTimeout(timeoutId);
        if (cancelled) return;
        if (res.ok) {
          setVerified("verified");
        } else if (res.status === 403) {
          setVerified("denied");
          await getSupabaseBrowserClient().auth.signOut();
        } else {
          // Other errors — treat as unverified but don't sign out
          setVerified("idle");
        }
      } catch {
        if (!cancelled) setVerified("idle");
      }
    };
    verifyWithBackend();
    return () => { cancelled = true; };
  }, [user, verified]);

  const signInWithGoogle = async () => {
    const redirectTo = `${window.location.origin}/auth/callback`;
    const { error } = await getSupabaseBrowserClient().auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo },
    });

    if (error) {
      throw error;
    }
  };

  const signOut = async () => {
    await getSupabaseBrowserClient().auth.signOut();
  };

  return (
    <AuthContext.Provider value={{ user, loading, verified, signInWithGoogle, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
