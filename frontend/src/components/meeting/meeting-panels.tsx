"use client";

import * as React from "react";

import {
  ChevronDownIcon,
  ChevronUpIcon,
  MessageSquareIcon,
  MicOffIcon,
  MoreVerticalIcon,
  SearchIcon,
  SendIcon,
  UserPlusIcon,
  XIcon,
} from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { cn } from "cn";

type PanelParticipant = {
  id: string;
  name: string;
  role?: string;
  isMuted?: boolean;
  isYou?: boolean;
};

type ChatMessage = {
  id: string;
  author: string;
  text: string;
  time: string;
};

const PANEL_BASE =
  "flex w-full max-w-full flex-col gap-4 rounded-xl border bg-card p-4 text-card-foreground shadow-sm";

function PanelHeader({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose?: () => void;
  children?: React.ReactNode;
}) {
  return (
    <>
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-heading text-base font-medium">{title}</h2>
        {onClose ? (
          <Button variant="ghost" size="icon-sm" aria-label={`Close ${title}`} onClick={onClose}>
            <XIcon />
          </Button>
        ) : null}
      </div>
      {children}
    </>
  );
}

function ParticipantRow({ participant }: { participant: PanelParticipant }) {
  const { name, role, isMuted = false, isYou = false } = participant;

  return (
    <li className="hover:bg-muted flex items-center gap-3 rounded-lg px-2 py-2 transition-colors">
      <Avatar className="size-8">
        <AvatarFallback className="text-xs">
          {name
            .split(/\s+/)
            .slice(0, 2)
            .map((part) => part[0]?.toUpperCase() ?? "")
            .join("")}
        </AvatarFallback>
      </Avatar>
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="truncate text-sm font-medium">
          {name}
          {isYou ? <span className="text-muted-foreground font-normal"> (You)</span> : null}
        </span>
        {role ? <span className="text-muted-foreground truncate text-xs">{role}</span> : null}
      </div>
      {isMuted ? (
        <MicOffIcon aria-label={`${name} is muted`} className="text-destructive size-4" />
      ) : null}
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label={`More actions for ${name}`}
        className="rounded-full"
      >
        <MoreVerticalIcon />
      </Button>
    </li>
  );
}

function PeoplePanel({
  participants,
  onAddPeople,
  onClose,
  className,
}: {
  participants: PanelParticipant[];
  onAddPeople?: () => void;
  onClose?: () => void;
  className?: string;
}) {
  const [query, setQuery] = React.useState("");
  const [isGroupOpen, setIsGroupOpen] = React.useState(true);

  const filtered = participants.filter((participant) =>
    participant.name.toLowerCase().includes(query.trim().toLowerCase()),
  );

  return (
    <aside aria-label="People" className={cn(PANEL_BASE, className)}>
      <PanelHeader title="People" onClose={onClose}>
        <div className="flex flex-col gap-3">
          <Button onClick={onAddPeople} className="w-fit rounded-full">
            <UserPlusIcon data-icon="inline-start" />
            Add people
          </Button>
          <div className="relative">
            <SearchIcon
              aria-hidden="true"
              className="text-muted-foreground absolute top-1/2 left-2.5 size-4 -translate-y-1/2"
            />
            <Input
              type="search"
              aria-label="Search for people"
              placeholder="Search for people"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="pl-8"
            />
          </div>
        </div>
      </PanelHeader>

      <div className="flex flex-col gap-2">
        <p className="text-muted-foreground px-1 text-xs font-medium tracking-wide uppercase">
          In this meet
        </p>
        <div className="rounded-lg border">
          <button
            type="button"
            aria-expanded={isGroupOpen}
            onClick={() => setIsGroupOpen((open) => !open)}
            className="hover:bg-muted focus-visible:ring-ring/50 flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors focus-visible:ring-3 focus-visible:outline-none"
          >
            <span className="inline-flex items-center gap-2">
              Contributors
              <Badge variant="secondary">{participants.length}</Badge>
            </span>
            {isGroupOpen ? <ChevronUpIcon /> : <ChevronDownIcon />}
          </button>
          {isGroupOpen ? (
            <ul className="flex flex-col border-t">
              {filtered.map((participant) => (
                <ParticipantRow key={participant.id} participant={participant} />
              ))}
              {filtered.length === 0 ? (
                <li className="text-muted-foreground px-3 py-4 text-center text-sm">
                  No people match your search.
                </li>
              ) : null}
            </ul>
          ) : null}
        </div>
      </div>
    </aside>
  );
}

function ChatPanel({
  messages = [],
  canSend = true,
  onSend,
  onToggleCanSend,
  onClose,
  className,
}: {
  messages?: ChatMessage[];
  canSend?: boolean;
  onSend?: (text: string) => void;
  onToggleCanSend?: (enabled: boolean) => void;
  onClose?: () => void;
  className?: string;
}) {
  const [draft, setDraft] = React.useState("");
  const [allowMessages, setAllowMessages] = React.useState(true);

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const text = draft.trim();
    if (!text) return;
    onSend?.(text);
    setDraft("");
  };

  return (
    <aside aria-label="In-call messages" className={cn(PANEL_BASE, "min-h-0", className)}>
      <PanelHeader title="In-call messages" onClose={onClose} />

      <div className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2.5">
        <Label htmlFor="allow-messages" className="text-sm font-normal">
          Let participants send messages
        </Label>
        <Switch
          id="allow-messages"
          checked={allowMessages}
          onCheckedChange={(checked) => {
            setAllowMessages(checked);
            onToggleCanSend?.(checked);
          }}
        />
      </div>

      {!allowMessages || !canSend ? (
        <Alert variant="info">
          <AlertTitle>Continuous chat is turned off</AlertTitle>
          <AlertDescription>
            Messages will not be saved for meeting participants when the call ends. You can pin a
            message to make it visible for people who join later.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="min-h-32 flex-1 overflow-y-auto">
        {messages.length > 0 ? (
          <ul className="flex flex-col gap-3">
            {messages.map((message) => (
              <li key={message.id} className="flex flex-col gap-0.5 px-1">
                <span className="text-xs font-medium">
                  {message.author}
                  <span className="text-muted-foreground ml-2 font-normal">{message.time}</span>
                </span>
                <span className="text-sm">{message.text}</span>
              </li>
            ))}
          </ul>
        ) : (
          <Empty className="border">
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <MessageSquareIcon />
              </EmptyMedia>
              <EmptyTitle>No messages yet</EmptyTitle>
              <EmptyDescription>Say hello or share the agenda.</EmptyDescription>
            </EmptyHeader>
          </Empty>
        )}
      </div>

      <form onSubmit={submit} className="flex items-center gap-2">
        <Input
          aria-label="Send a message"
          placeholder="Send a message"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
        <Button
          type="submit"
          variant="outline"
          size="icon"
          aria-label="Send message"
          disabled={!draft.trim()}
        >
          <SendIcon />
        </Button>
      </form>
    </aside>
  );
}

export { PeoplePanel, ChatPanel };
export type { PanelParticipant, ChatMessage };
