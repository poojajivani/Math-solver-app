import { createClient } from "@supabase/supabase-js";

const FALLBACK_SUPABASE_URL = "https://ftpheurhvwozdknvpbyt.supabase.co";
const FALLBACK_SUPABASE_ANON_KEY = "sb_publishable_-WDt8htQIzLkqDOehU_1Gg_v57QX8N9";

const supabaseUrl =
  process.env.REACT_APP_SUPABASE_URL?.trim() || FALLBACK_SUPABASE_URL;

const supabaseAnonKey =
  process.env.REACT_APP_SUPABASE_ANON_KEY?.trim() || FALLBACK_SUPABASE_ANON_KEY;

const isValidSupabaseUrl = /^https:\/\/[a-z0-9-]+\.supabase\.co$/i.test(
  supabaseUrl
);

export const supabaseConfigError = !supabaseUrl
  ? "Missing REACT_APP_SUPABASE_URL."
  : !isValidSupabaseUrl
    ? "REACT_APP_SUPABASE_URL must look like https://your-project-id.supabase.co."
    : !supabaseAnonKey
      ? "Missing REACT_APP_SUPABASE_ANON_KEY."
      : "";

export const isSupabaseConfigured = !supabaseConfigError;

export const supabase = isSupabaseConfigured
  ? createClient(supabaseUrl, supabaseAnonKey)
  : null;
