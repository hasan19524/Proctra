import { HandIcon, MicOffIcon, PinIcon } from "lucide-react";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "cn";

import {
  ConnectionQuality,
  type ConnectionQualityLevel,
} from "@/components/meeting/status-indicator";

type ParticipantTileProps = {
  name: string;
  initials?: string;
  avatarSrc?: string;
  isMuted?: boolean;
  isCameraOff?: boolean;
  isSpeaking?: boolean;
  isHandRaised?: boolean;
  isScreenSharing?: boolean;
  isHost?: boolean;
  isPinned?: boolean;
  connection?: ConnectionQualityLevel;
  onPin?: () => void;
  className?: string;
};

function participantInitials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

function ParticipantTile({
  name,
  initials,
  avatarSrc,
  isMuted = false,
  isCameraOff = false,
  isSpeaking = false,
  isHandRaised = false,
  isScreenSharing = false,
  isHost = false,
  isPinned = false,
  connection,
  onPin,
  className,
}: ParticipantTileProps) {
  const fallback = initials ?? (participantInitials(name) || "?");

  return (
    <div
      role="group"
      aria-label={`${name}'s video`}
      data-speaking={isSpeaking || undefined}
      className={cn(
        "group bg-card text-card-foreground relative flex aspect-video min-w-0 flex-col overflow-hidden rounded-xl border shadow-sm transition-shadow duration-200",
        isSpeaking && "ring-ring ring-2",
        isPinned && "border-primary/60",
        className,
      )}
    >
      <div className="bg-muted relative flex flex-1 items-center justify-center">
        <div className="text-muted-foreground flex flex-col items-center gap-2">
          <Avatar className="size-16">
            {avatarSrc ? <AvatarImage src={avatarSrc} alt="" /> : null}
            <AvatarFallback className="bg-background text-base">{fallback}</AvatarFallback>
          </Avatar>
          <span className="text-xs">
            {isCameraOff ? "Camera off" : isScreenSharing ? "Sharing screen" : "Video preview"}
          </span>
        </div>

        {isMuted ? (
          <span
            aria-label={`${name} is muted`}
            className="bg-background/80 text-destructive absolute top-2 right-2 flex size-8 items-center justify-center rounded-full backdrop-blur-sm"
          >
            <MicOffIcon aria-hidden="true" className="size-4" />
          </span>
        ) : null}

        {connection ? (
          <ConnectionQuality
            quality={connection}
            showLabel={false}
            className="bg-background/80 absolute right-2 bottom-2 rounded-md px-1.5 py-1 backdrop-blur-sm"
          />
        ) : null}

        {onPin ? (
          <div className="absolute inset-x-0 top-1/2 flex -translate-y-1/2 justify-center opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100">
            <Tooltip>
              <TooltipTrigger
                render={
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={isPinned ? `Unpin ${name}` : `Pin ${name}`}
                    className="bg-background/70 rounded-full backdrop-blur-sm"
                  />
                }
              >
                <PinIcon />
              </TooltipTrigger>
              <TooltipContent>{isPinned ? "Unpin" : "Pin"}</TooltipContent>
            </Tooltip>
          </div>
        ) : null}
      </div>

      <div className="bg-background/70 text-foreground absolute bottom-2 left-2 flex max-w-[calc(100%-1rem)] items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium backdrop-blur-sm">
        <span className="truncate">{name}</span>
        {isHost ? (
          <Badge variant="secondary" className="h-4 px-1.5 text-[0.65rem]">
            Host
          </Badge>
        ) : null}
        {isHandRaised ? (
          <Badge variant="warning" className="h-4 gap-1 px-1.5 text-[0.65rem]">
            <HandIcon data-icon="inline-start" aria-hidden="true" />
            Hand
          </Badge>
        ) : null}
      </div>
    </div>
  );
}

export { ParticipantTile };
export type { ParticipantTileProps };
