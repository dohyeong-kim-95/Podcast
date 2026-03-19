"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  GoogleAuthProvider,
  onAuthStateChanged,
  signInWithRedirect,
  getRedirectResult,
  signOut as firebaseSignOut,
  type User,
} from "firebase/auth";
import { getFirebaseAuth } from "./firebase";

interface AuthContextType {
  user: User | null;
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

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8080";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [verified, setVerified] = useState<"idle" | "pending" | "verified" | "denied">("idle");

  // Handle redirect result on mount
  useEffect(() => {
    const auth = getFirebaseAuth();
    getRedirectResult(auth).catch(() => {
      // No redirect result or error — ignore
    });
  }, []);

  useEffect(() => {
    const auth = getFirebaseAuth();
    const unsubscribe = onAuthStateChanged(auth, (u) => {
      setUser(u);
      setLoading(false);
      if (!u) {
        setVerified("idle");
      }
    });
    return unsubscribe;
  }, []);

  // Verify with backend when user signs in
  useEffect(() => {
    if (!user) return;
    if (verified === "verified" || verified === "pending") return;

    let cancelled = false;
    const verifyWithBackend = async () => {
      setVerified("pending");
      try {
        const token = await user.getIdToken();
        const res = await fetch(`${API_BASE}/api/auth/verify`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        });
        if (cancelled) return;
        if (res.ok) {
          setVerified("verified");
        } else if (res.status === 403) {
          setVerified("denied");
          await firebaseSignOut(getFirebaseAuth());
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
    const provider = new GoogleAuthProvider();
    await signInWithRedirect(getFirebaseAuth(), provider);
  };

  const signOut = async () => {
    await firebaseSignOut(getFirebaseAuth());
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
