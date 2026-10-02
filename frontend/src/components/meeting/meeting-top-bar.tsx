import { InfoIcon, UsersIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "cn";

function MeetingTopBar({
  code,
  time,
  participantCount,
  onShowDetails,
  onOpenPeople,
  className,
}: {
  code: string;
  time: string;
  participantCount: number;
  onShowDetails?: () => void;
  onOpenPeople?: () => void;
  className?: string;
}) {
  return (
    <header
      className={cn(
        "flex h-12 shrink-0 items-center justify-between gap-3 px-3 sm:px-4",
        className,
      )}
    >
      <div className="flex min-w-0 items-center gap-2 text-sm">
        <span className="text-muted-foreground tabular-nums" suppressHydrationWarning>
          {time}
        </span>
        <span aria-hidden="true" className="text-muted-foreground/50">
          |
        </span>
        <span className="truncate font-mono">{code}</span>
        <Button variant="ghost" size="icon-sm" aria-label="Meeting details" onClick={onShowDetails}>
          <InfoIcon />
        </Button>
      </div>

      <Button
        variant="secondary"
        size="sm"
        aria-label={`Show people, ${participantCount} in this meet`}
        onClick={onOpenPeople}
        className="gap-2 rounded-full"
      >
        <span
          aria-hidden="true"
          className="bg-primary text-primary-foreground flex size-5 items-center justify-center rounded-full text-[0.6rem] font-semibold"
        >
          P
        </span>
        <UsersIcon aria-hidden="true" />
        <span className="tabular-nums">{participantCount}</span>
      </Button>
    </header>
  );
}

export { MeetingTopBar };
