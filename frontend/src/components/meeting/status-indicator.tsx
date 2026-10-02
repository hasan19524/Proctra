import { Badge } from "@/components/ui/badge";
import { cn } from "cn";

type MeetingStatus = "connecting" | "connected" | "reconnecting" | "failed";

type ConnectionQuality = "excellent" | "good" | "fair" | "poor" | "offline";

const MEETING_STATUS: Record<
  MeetingStatus,
  { label: string; variant: "success" | "warning" | "destructive" }
> = {
  connecting: { label: "Connecting", variant: "warning" },
  connected: { label: "Connected", variant: "success" },
  reconnecting: { label: "Reconnecting", variant: "warning" },
  failed: { label: "Connection lost", variant: "destructive" },
};

const QUALITY_LABEL: Record<ConnectionQuality, string> = {
  excellent: "Excellent connection",
  good: "Good connection",
  fair: "Unstable connection",
  poor: "Poor connection",
  offline: "Offline",
};

function StatusIndicator({ status, className }: { status: MeetingStatus; className?: string }) {
  const { label, variant } = MEETING_STATUS[status];

  return (
    <Badge variant={variant} className={cn("gap-1.5", className)}>
      <span
        aria-hidden="true"
        className={cn(
          "size-1.5 rounded-full bg-current",
          status === "connecting" || status === "reconnecting" || status === "connected"
            ? "animate-pulse"
            : undefined,
        )}
      />
      {label}
    </Badge>
  );
}

function ConnectionQuality({
  quality,
  showLabel = true,
  className,
}: {
  quality: ConnectionQuality;
  showLabel?: boolean;
  className?: string;
}) {
  const label = QUALITY_LABEL[quality];
  const variant =
    quality === "offline" || quality === "poor"
      ? "destructive"
      : quality === "fair"
        ? "warning"
        : "success";
  const bars = { excellent: 4, good: 3, fair: 2, poor: 1, offline: 0 }[quality];

  return (
    <span
      role="status"
      aria-label={label}
      className={cn(
        "inline-flex items-center gap-1.5 text-xs font-medium",
        variant === "destructive" && "text-destructive",
        variant === "warning" && "text-warning",
        variant === "success" && "text-success",
        className,
      )}
    >
      <span aria-hidden="true" className="flex h-3.5 items-end gap-px">
        {[1, 2, 3, 4].map((bar) => (
          <span
            key={bar}
            className={cn(
              "w-[3px] rounded-sm bg-current",
              bar === 1 && "h-1",
              bar === 2 && "h-1.5",
              bar === 3 && "h-2.5",
              bar === 4 && "h-3.5",
              bar > bars && "opacity-30",
            )}
          />
        ))}
      </span>
      {showLabel ? <span className="sr-only sm:not-sr-only">{label}</span> : null}
    </span>
  );
}

function LiveIndicator({ className }: { className?: string }) {
  return (
    <Badge variant="destructive" className={cn("gap-1.5", className)}>
      <span aria-hidden="true" className="size-1.5 animate-pulse rounded-full bg-current" />
      Live
    </Badge>
  );
}

export { StatusIndicator, ConnectionQuality, LiveIndicator };
export type { MeetingStatus, ConnectionQuality as ConnectionQualityLevel };
