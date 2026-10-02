import { LinkIcon, RefreshCwIcon, TriangleAlertIcon, UserPlusIcon } from "lucide-react";

import { Alert, AlertDescription, AlertAction, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "cn";

function MeetingLoadingState({
  label = "Connecting to meet…",
  tiles = 3,
  className,
}: {
  label?: string;
  tiles?: number;
  className?: string;
}) {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-live="polite"
      className={cn("flex w-full flex-col items-center gap-4", className)}
    >
      <div className="grid w-full gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: tiles }, (_, index) => (
          <Skeleton key={index} className="aspect-video w-full rounded-xl" />
        ))}
      </div>
      <div className="text-muted-foreground flex items-center gap-2 text-sm">
        <Spinner aria-hidden="true" />
        {label}
      </div>
    </div>
  );
}

function MeetingErrorState({
  title = "Could not join the meet",
  description = "Check your connection and try again. Your camera and mic were not changed.",
  onRetry,
  className,
}: {
  title?: string;
  description?: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <Alert variant="destructive" className={cn("text-left", className)}>
      <TriangleAlertIcon />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>{description}</AlertDescription>
      {onRetry ? (
        <AlertAction>
          <Button variant="outline" size="sm" onClick={onRetry}>
            <RefreshCwIcon data-icon="inline-start" />
            Retry
          </Button>
        </AlertAction>
      ) : null}
    </Alert>
  );
}

function MeetingEmptyState({
  title = "No one else is here yet",
  description = "Share the invite link and people will appear in this meet as they join.",
  actionLabel = "Copy invite link",
  onAction,
  className,
}: {
  title?: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}) {
  return (
    <Empty className={cn("border", className)}>
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <UserPlusIcon />
        </EmptyMedia>
        <EmptyTitle>{title}</EmptyTitle>
        <EmptyDescription>{description}</EmptyDescription>
      </EmptyHeader>
      {onAction ? (
        <EmptyContent>
          <Button variant="outline" onClick={onAction}>
            <LinkIcon data-icon="inline-start" />
            {actionLabel}
          </Button>
        </EmptyContent>
      ) : null}
    </Empty>
  );
}

export { MeetingLoadingState, MeetingErrorState, MeetingEmptyState };
