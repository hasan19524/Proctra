"use client";

import * as React from "react";

import {
  HandIcon,
  LayoutGridIcon,
  LockIcon,
  MessageSquareIcon,
  MicIcon,
  MicOffIcon,
  MonitorUpIcon,
  MoreVerticalIcon,
  PhoneOffIcon,
  ScreenShareIcon,
  SettingsIcon,
  SmileIcon,
  StickyNoteIcon,
  VideoIcon,
  VideoOffIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Kbd } from "@/components/ui/kbd";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "cn";

type MeetingControlsState = {
  isMicOn: boolean;
  isCameraOn: boolean;
  isScreenSharing: boolean;
  isHandRaised: boolean;
};

type MoreAction = "captions" | "settings" | "notes" | "host-controls";

type MeetingControlsProps = {
  state: MeetingControlsState;
  onToggleMic: () => void;
  onToggleCamera: () => void;
  onToggleScreenShare: () => void;
  onToggleHand: () => void;
  onOpenChat: () => void;
  onToggleReactions: () => void;
  onLeave: () => void;
  onMoreAction?: (action: MoreAction) => void;
  isReactionsOpen?: boolean;
  isLeaving?: boolean;
  isBusy?: boolean;
  className?: string;
};

type ControlTone = "neutral" | "danger" | "info" | "warning" | "brand";

const CONTROL_TONES: Record<ControlTone, string> = {
  neutral: "hover:bg-muted hover:text-foreground",
  danger: "bg-destructive/10 text-destructive hover:bg-destructive/20",
  info: "bg-info/10 text-info hover:bg-info/20",
  warning: "bg-warning/10 text-warning hover:bg-warning/20",
  brand: "bg-primary/10 text-primary hover:bg-primary/15",
};

function WarningBadge() {
  return (
    <span
      aria-hidden="true"
      className="bg-warning text-warning-foreground ring-card absolute top-0 right-0 flex size-3.5 items-center justify-center rounded-full text-[0.55rem] leading-none font-bold ring-2"
    >
      !
    </span>
  );
}

function MeetingControl({
  label,
  shortcut,
  tone = "neutral",
  pressed,
  showWarning = false,
  onClick,
  disabled,
  children,
}: {
  label: string;
  shortcut?: string;
  tone?: ControlTone;
  pressed?: boolean;
  showWarning?: boolean;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant="ghost"
            size="icon-xl"
            aria-label={label}
            aria-pressed={pressed}
            onClick={onClick}
            disabled={disabled}
            className={cn("relative rounded-full", CONTROL_TONES[tone])}
          >
            {children}
            {showWarning ? <WarningBadge /> : null}
          </Button>
        }
      />
      <TooltipContent>
        <span className="inline-flex items-center gap-2">
          {label}
          {shortcut ? <Kbd>{shortcut}</Kbd> : null}
        </span>
      </TooltipContent>
    </Tooltip>
  );
}

function MeetingControls({
  state,
  onToggleMic,
  onToggleCamera,
  onToggleScreenShare,
  onToggleHand,
  onOpenChat,
  onToggleReactions,
  onLeave,
  onMoreAction,
  isReactionsOpen = false,
  isLeaving = false,
  isBusy = false,
  className,
}: MeetingControlsProps) {
  const { isMicOn, isCameraOn, isScreenSharing, isHandRaised } = state;

  return (
    <div
      role="toolbar"
      aria-label="Meeting controls"
      className={cn(
        "bg-card/95 flex w-fit max-w-full items-center gap-1 overflow-x-auto rounded-full border px-2 py-2 shadow-lg backdrop-blur sm:gap-1.5 sm:px-3",
        className,
      )}
    >
      <MeetingControl
        label={isMicOn ? "Turn off microphone (M)" : "Turn on microphone (M)"}
        shortcut="M"
        tone={isMicOn ? "neutral" : "danger"}
        pressed={isMicOn}
        showWarning={!isMicOn}
        onClick={onToggleMic}
        disabled={isBusy}
      >
        {isMicOn ? <MicIcon /> : <MicOffIcon />}
      </MeetingControl>

      <MeetingControl
        label={isCameraOn ? "Turn off camera (V)" : "Turn on camera (V)"}
        shortcut="V"
        tone={isCameraOn ? "neutral" : "danger"}
        pressed={isCameraOn}
        showWarning={!isCameraOn}
        onClick={onToggleCamera}
        disabled={isBusy}
      >
        {isCameraOn ? <VideoIcon /> : <VideoOffIcon />}
      </MeetingControl>

      <MeetingControl
        label={isScreenSharing ? "Stop sharing (S)" : "Share screen (S)"}
        shortcut="S"
        tone={isScreenSharing ? "info" : "neutral"}
        pressed={isScreenSharing}
        onClick={onToggleScreenShare}
        disabled={isBusy}
      >
        {isScreenSharing ? <ScreenShareIcon /> : <MonitorUpIcon />}
      </MeetingControl>

      <MeetingControl
        label="Send a reaction"
        tone={isReactionsOpen ? "brand" : "neutral"}
        pressed={isReactionsOpen}
        onClick={onToggleReactions}
        disabled={isBusy}
      >
        <SmileIcon />
      </MeetingControl>

      <MeetingControl label="Chat (C)" shortcut="C" onClick={onOpenChat} disabled={isBusy}>
        <MessageSquareIcon />
      </MeetingControl>

      <MeetingControl
        label={isHandRaised ? "Lower hand (R)" : "Raise hand (R)"}
        shortcut="R"
        tone={isHandRaised ? "warning" : "neutral"}
        pressed={isHandRaised}
        onClick={onToggleHand}
        disabled={isBusy}
      >
        <HandIcon />
      </MeetingControl>

      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              variant="ghost"
              size="icon-xl"
              aria-label="More options"
              disabled={isBusy}
              className="rounded-full"
            >
              <MoreVerticalIcon />
            </Button>
          }
        />
        <DropdownMenuContent align="center">
          <DropdownMenuItem onClick={() => onMoreAction?.("captions")}>
            Turn on captions
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => onMoreAction?.("settings")}>
            <SettingsIcon data-icon="inline-start" />
            Settings
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => onMoreAction?.("notes")}>
            <StickyNoteIcon data-icon="inline-start" />
            Notes
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => onMoreAction?.("host-controls")}>
            <LockIcon data-icon="inline-start" />
            Host controls
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Separator orientation="vertical" className="mx-1 h-8" />

      <Button
        variant="destructive-solid"
        size="icon-xl"
        onClick={onLeave}
        disabled={isLeaving || isBusy}
        aria-label={isLeaving ? "Leaving meeting" : "Leave meeting"}
        className="rounded-full"
      >
        {isLeaving ? <Spinner aria-hidden="true" /> : <PhoneOffIcon aria-hidden="true" />}
      </Button>
    </div>
  );
}

function UtilityCluster({
  onOpenChat,
  onOpenPeople,
  onToggleHostControls,
  isChatOpen,
  isPeopleOpen,
  isHostControlsOn,
  className,
}: {
  onOpenChat: () => void;
  onOpenPeople: () => void;
  onToggleHostControls: () => void;
  isChatOpen?: boolean;
  isPeopleOpen?: boolean;
  isHostControlsOn?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "bg-card/95 flex items-center gap-1 rounded-full border p-1.5 shadow-lg backdrop-blur",
        className,
      )}
    >
      <Button
        variant={isChatOpen ? "secondary" : "ghost"}
        size="icon-sm"
        aria-label="Open chat"
        aria-pressed={isChatOpen}
        onClick={onOpenChat}
        className="rounded-full"
      >
        <MessageSquareIcon />
      </Button>
      <Button
        variant={isPeopleOpen ? "secondary" : "ghost"}
        size="icon-sm"
        aria-label="Show people"
        aria-pressed={isPeopleOpen}
        onClick={onOpenPeople}
        className="rounded-full"
      >
        <LayoutGridIcon />
      </Button>
      <Button
        variant={isHostControlsOn ? "secondary" : "ghost"}
        size="icon-sm"
        aria-label="Host controls"
        aria-pressed={isHostControlsOn}
        onClick={onToggleHostControls}
        className="rounded-full"
      >
        <LockIcon />
      </Button>
    </div>
  );
}

export { MeetingControls, MeetingControl, UtilityCluster };
export type { MeetingControlsProps, MeetingControlsState, MoreAction };
