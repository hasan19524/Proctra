"use client";

import { useSearchParams } from "next/navigation";

/**
 * Sanitise a ?next= destination: same-origin, single-slash path only.
 * Open-redirect guard — no protocol, no `//` authority, no backslash tricks.
 */
export function sanitizeNextPath(raw: string | null): string | null {
  if (!raw) return null;
  if (!raw.startsWith("/") || raw.startsWith("//") || raw.includes("\\")) return null;
  return raw;
}

/** Sanitised in-app destination from ?next= at the current URL, or null. */
export function readNextPath(): string | null {
  if (typeof window === "undefined") return null;
  return sanitizeNextPath(new URLSearchParams(window.location.search).get("next"));
}

/**
 * `?next=…` query string (or "") to carry across the login/register hops.
 * Uses `useSearchParams` (prerender-safe inside a Suspense boundary) rather
 * than reading `window.location` in an effect, which the react-hooks
 * `set-state-in-effect` rule rejects.
 */
export function useNextQuery(): string {
  const searchParams = useSearchParams();
  const dest = sanitizeNextPath(searchParams.get("next"));
  return dest ? `?next=${encodeURIComponent(dest)}` : "";
}
