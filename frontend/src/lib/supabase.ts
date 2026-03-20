"use client";

import {
  createClient,
  type Session,
  type SupabaseClient,
  type User,
} from "@supabase/supabase-js";

let browserClient: SupabaseClient | undefined;

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

function getRequiredEnv(name: string, value: string | undefined): string {
  if (!value) {
    throw new Error(`${name}가 설정되지 않았습니다`);
  }
  return value;
}

export function getSupabaseBrowserClient(): SupabaseClient {
  if (!browserClient) {
    browserClient = createClient(
      getRequiredEnv("NEXT_PUBLIC_SUPABASE_URL", supabaseUrl),
      getRequiredEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", supabaseAnonKey),
      {
        auth: {
          flowType: "pkce",
          persistSession: true,
          autoRefreshToken: true,
          detectSessionInUrl: false,
        },
      },
    );
  }

  return browserClient;
}

export async function getSupabaseSession(): Promise<Session | null> {
  const { data, error } = await getSupabaseBrowserClient().auth.getSession();
  if (error) {
    throw error;
  }
  return data.session;
}

export async function getSupabaseAccessToken(): Promise<string> {
  const session = await getSupabaseSession();
  if (!session?.access_token) {
    throw new Error("Not authenticated");
  }
  return session.access_token;
}

export type SupabaseAuthUser = User;
