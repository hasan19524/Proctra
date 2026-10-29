"use client";

export type ShareOutcome = "shared" | "copied" | "cancelled" | "failed";

/**
 * The invite is the link itself: try the native share sheet first (mobile →
 * WhatsApp/Telegram/whatever), fall back to copying the link on desktop.
 *
 * - `shared`    — the OS share sheet completed (no toast needed)
 * - `cancelled` — the user dismissed the share sheet (no toast needed)
 * - `copied`    — link is on the clipboard; tell the user where it went
 * - `failed`    — nothing worked; show the link so they can copy manually
 */
export async function shareOrCopyLink(url: string, title: string): Promise<ShareOutcome> {
  if (typeof navigator === "undefined") return "failed";

  if (typeof navigator.share === "function") {
    try {
      await navigator.share({ title, url });
      return "shared";
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return "cancelled";
      // Unsupported/failed share (exotic UA, insecure context) → copy instead.
    }
  }

  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(url);
      return "copied";
    } catch {
      // Clipboard denied (permissions/insecure context) → failed below.
    }
  }
  return "failed";
}
