"use client";

import * as React from "react";

import { DownloadIcon, ShieldAlertIcon, ShieldCheckIcon, XIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { meetingsApi } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import { cn } from "cn";
import type { ProctorFlag } from "@/hooks/use-meeting-ws";
import type { ProctorStatus } from "@/lib/proctor/types";

/** Signal → short badge label (mirrors server's PROCTOR_LABELS). */
const SIGNAL_BADGES: Record<string, { label: string; tone: "warn" | "danger" }> = {
  looking_away: { label: "Looking away", tone: "warn" },
  no_face: { label: "No face", tone: "danger" },
  multiple_faces: { label: "Second person", tone: "danger" },
  speaking: { label: "Speaking", tone: "warn" },
  eyes_closed: { label: "Eyes closed", tone: "warn" },
  tab_hidden: { label: "Left exam tab", tone: "danger" },
  video_blur: { label: "Blurry video", tone: "warn" },
};

function flagTime(flag: ProctorFlag): string {
  const minutes = Math.max(0, flag.minute);
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

export interface IntegrityPanelProps {
  flags: ProctorFlag[];
  className?: string;
  meetingCode: string;
  onClose: () => void;
}

/**
 * Host-only live integrity panel for a proctored exam (Phase 16).
 *
 * Shows the running flag feed (each flag carries its label and score delta),
 * a per-student score rollup, and the CSV report download. Students never
 * receive this data — the server filters `proctor.flag` frames to the host.
 */
export function IntegrityPanel({ flags, className, meetingCode, onClose }: IntegrityPanelProps) {
  const [downloading, setDownloading] = React.useState(false);

  // Per-student score rollup (same math the server uses: sum of points).
  const scores = React.useMemo(() => {
    const map = new Map<string, { name: string; score: number; count: number }>();
    for (const flag of flags) {
      const entry = map.get(flag.user_id) ?? { name: flag.name, score: 0, count: 0 };
      entry.score += flag.points;
      entry.count += 1;
      map.set(flag.user_id, entry);
    }
    return [...map.values()].sort((a, b) => b.score - a.score || a.name.localeCompare(b.name));
  }, [flags]);

  // Newest first for display.
  const recentFlags = React.useMemo(() => [...flags].reverse(), [flags]);

  const handleDownload = React.useCallback(async () => {
    setDownloading(true);
    try {
      await meetingsApi.downloadReportCsv(meetingCode);
      toast.add({ type: "success", title: "Report downloaded" });
    } catch {
      toast.add({
        type: "error",
        title: "Download failed",
        description: "Could not download the report — check your connection and retry.",
      });
    } finally {
      setDownloading(false);
    }
  }, [meetingCode]);

  return (
    <section
      aria-label="Exam integrity"
      className={cn(
        "bg-card flex h-full w-full flex-col rounded-xl border shadow-sm",
        className,
      )}
    >
      <header className="border-border flex items-center justify-between gap-2 border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <ShieldAlertIcon className="text-warning size-4" aria-hidden="true" />
          <h2 className="text-sm font-semibold">Exam integrity</h2>
          <span className="bg-muted text-muted-foreground rounded-full px-2 py-0.5 text-xs">
            {flags.length} flag{flags.length === 1 ? "" : "s"}
          </span>
        </div>
        <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close integrity panel">
          <XIcon className="size-4" />
        </Button>
      </header>

      {/* Score summary per student */}
      {scores.length > 0 ? (
        <div className="border-border border-b px-4 py-3">
          <h3 className="text-muted-foreground mb-2 text-xs font-medium uppercase tracking-wide">
            Scores
          </h3>
          <ul className="flex flex-col gap-1.5">
            {scores.map((entry) => (
              <li key={entry.name} className="flex items-center justify-between gap-2 text-sm">
                <span className="truncate">{entry.name}</span>
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-xs font-medium tabular-nums",
                    entry.score >= 10
                      ? "bg-destructive/10 text-destructive"
                      : entry.score >= 4
                        ? "bg-warning/10 text-warning"
                        : "bg-muted text-muted-foreground",
                  )}
                >
                  {entry.score} pts · {entry.count} event{entry.count === 1 ? "" : "s"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Live flag feed */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        {recentFlags.length === 0 ? (
          <div className="text-muted-foreground flex h-full flex-col items-center justify-center gap-2 py-8 text-center text-sm">
            <ShieldCheckIcon className="size-8 opacity-50" aria-hidden="true" />
            <p>No flags yet</p>
            <p className="text-xs">The vision model is watching every student in this room.</p>
          </div>
        ) : (
          <ul className="flex flex-col gap-1.5" aria-live="polite">
            {recentFlags.map((flag) => {
              const badge = SIGNAL_BADGES[flag.signal] ?? { label: flag.signal, tone: "warn" as const };
              return (
                <li
                  key={flag.id}
                  className="bg-muted/50 flex items-center justify-between gap-2 rounded-md px-2.5 py-1.5 text-xs"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="text-muted-foreground font-mono tabular-nums">
                      {flagTime(flag)}
                    </span>
                    <span className="truncate font-medium">{flag.name}</span>
                    <span
                      className={cn(
                        "rounded-full px-1.5 py-0.5 text-[0.65rem] font-medium whitespace-nowrap",
                        badge.tone === "danger"
                          ? "bg-destructive/10 text-destructive"
                          : "bg-warning/10 text-warning",
                      )}
                    >
                      {badge.label}
                    </span>
                  </div>
                  <span
                    className={cn(
                      "shrink-0 font-medium tabular-nums",
                      badge.tone === "danger" ? "text-destructive" : "text-warning",
                    )}
                  >
                    +{flag.points}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <footer className="border-border border-t px-4 py-3">
        <Button
          className="w-full"
          variant="outline"
          onClick={() => void handleDownload()}
          disabled={downloading}
        >
          <DownloadIcon className="size-4" aria-hidden="true" />
          {downloading ? "Preparing…" : "Download report (CSV)"}
        </Button>
      </footer>
    </section>
  );
}

export interface StudentProctorChipProps {
  status: ProctorStatus;
  message: string | null;
  onRetry: () => void;
}

/**
 * Small always-visible indicator for a student in a proctored exam (Phase 16).
 *
 * Communicates that proctoring is running (so nobody can claim they didn't
 * know), surfaces degradation (blurry camera / tab hidden), and offers a
 * retry when the engine fails to start.
 */
export function StudentProctorChip({ status, message, onRetry }: StudentProctorChipProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium shadow-sm backdrop-blur-sm",
        status === "active" && "bg-success/15 text-success border border-success/25",
        status === "degraded" && "bg-warning/15 text-warning border border-warning/25",
        status === "loading" && "bg-muted text-muted-foreground border border-border",
        status === "error" && "bg-destructive/15 text-destructive border border-destructive/25",
        status === "idle" && "bg-muted text-muted-foreground border border-border",
      )}
    >
      {status === "active" || status === "loading" ? (
        <ShieldCheckIcon className="size-3.5" aria-hidden="true" />
      ) : status === "error" ? (
        <ShieldAlertIcon className="size-3.5" aria-hidden="true" />
      ) : (
        <ShieldCheckIcon className="size-3.5 opacity-50" aria-hidden="true" />
      )}
      {status === "active" && "Proctoring active"}
      {status === "degraded" && (message ?? "Proctoring degraded")}
      {status === "loading" && "Starting proctoring…"}
      {status === "idle" && "Proctoring off"}
      {status === "error" ? (
        <>
          <span className="max-w-48 truncate">{message ?? "Proctoring error"}</span>
          <Button variant="ghost" size="xs" onClick={onRetry} className="ml-1 h-5 px-1.5 text-xs">
            Retry
          </Button>
        </>
      ) : null}
    </div>
  );
}
