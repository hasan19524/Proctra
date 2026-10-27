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
  UserMinusIcon,
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
import { Textarea } from "@/components/ui/textarea";
import type { NoteVisibility, WsNote } from "@/hooks/use-meeting-ws";
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

function ParticipantRow({
  participant,
  canManage = false,
  onMute,
  onRemove,
}: {
  participant: PanelParticipant;
  canManage?: boolean;
  onMute?: (id: string) => void;
  onRemove?: (id: string) => void;
}) {
  const { id, name, role, isMuted = false, isYou = false } = participant;

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
      {canManage && !isYou ? (
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={`Mute ${name}`}
            onClick={() => onMute?.(id)}
          >
            <MicOffIcon />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={`Remove ${name} from the meet`}
            onClick={() => onRemove?.(id)}
          >
            <UserMinusIcon />
          </Button>
        </div>
      ) : (
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={`More actions for ${name}`}
          className="rounded-full"
          disabled
        >
          <MoreVerticalIcon />
        </Button>
      )}
    </li>
  );
}

function PeoplePanel({
  participants,
  canManage = false,
  pendingJoins = [],
  onApproveJoin,
  onRejectJoin,
  onMute,
  onRemove,
  onAddPeople,
  onClose,
  className,
}: {
  participants: PanelParticipant[];
  canManage?: boolean;
  pendingJoins?: Array<{ user_id: string; name: string }>;
  onApproveJoin?: (id: string) => void;
  onRejectJoin?: (id: string) => void;
  onMute?: (id: string) => void;
  onRemove?: (id: string) => void;
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
        {canManage && pendingJoins.length > 0 ? (
          <div className="flex flex-col gap-1">
            <p className="text-muted-foreground px-1 text-xs font-medium tracking-wide uppercase">
              Waiting ({pendingJoins.length})
            </p>
            <div className="rounded-lg border">
              <ul className="flex flex-col">
                {pendingJoins.map((pending) => (
                  <li
                    key={pending.user_id}
                    className="flex items-center gap-3 border-b px-3 py-2 last:border-b-0"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{pending.name || "Guest"}</p>
                      <p className="text-muted-foreground text-xs">Waiting to join</p>
                    </div>
                    <div className="flex items-center gap-1">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => onApproveJoin?.(pending.user_id)}
                      >
                        Admit
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => onRejectJoin?.(pending.user_id)}
                      >
                        Deny
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ) : null}
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
                <ParticipantRow
                  key={participant.id}
                  participant={participant}
                  canManage={canManage}
                  onMute={onMute}
                  onRemove={onRemove}
                />
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
  allowChat = true,
  canManage = false,
  onSend,
  onToggleAllowChat,
  onClose,
  className,
}: {
  messages?: ChatMessage[];
  allowChat?: boolean;
  canManage?: boolean;
  onSend?: (text: string) => void;
  onToggleAllowChat?: (enabled: boolean) => void;
  onClose?: () => void;
  className?: string;
}) {
  const [draft, setDraft] = React.useState("");

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!allowChat) return;
    const text = draft.trim();
    if (!text) return;
    onSend?.(text);
    setDraft("");
  };

  return (
    <aside aria-label="In-call messages" className={cn(PANEL_BASE, "min-h-0", className)}>
      <PanelHeader title="In-call messages" onClose={onClose} />

      {canManage ? (
        <div className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2.5">
          <Label htmlFor="allow-messages" className="text-sm font-normal">
            Let participants send messages
          </Label>
          <Switch
            id="allow-messages"
            checked={allowChat}
            onCheckedChange={(checked) => onToggleAllowChat?.(checked)}
          />
        </div>
      ) : null}

      {!allowChat ? (
        <Alert variant="info">
          <AlertTitle>Chat is turned off</AlertTitle>
          <AlertDescription>
            The host has turned off chat for everyone in this meet.
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
          disabled={!allowChat}
        />
        <Button
          type="submit"
          variant="outline"
          size="icon"
          aria-label="Send message"
          disabled={!draft.trim() || !allowChat}
        >
          <SendIcon />
        </Button>
      </form>
    </aside>
  );
}

function NotesPanel({
  notes = [],
  isHost = false,
  connectionOpen = true,
  onSave,
  onClose,
  className,
}: {
  notes?: WsNote[];
  isHost?: boolean;
  connectionOpen?: boolean;
  onSave?: (visibility: NoteVisibility, text: string) => boolean;
  onClose?: () => void;
  className?: string;
}) {
  const [visibility, setVisibility] = React.useState<NoteVisibility>("all");
  const [drafts, setDrafts] = React.useState<Record<NoteVisibility, string>>({
    all: "",
    host_only: "",
  });
  const [dirty, setDirty] = React.useState<Record<NoteVisibility, boolean>>({
    all: false,
    host_only: false,
  });

  // Derive drafts from the wire: adopt server-confirmed content while the
  // local draft is clean, and clear `dirty` once an echo matches the draft.
  if (connectionOpen) {
    for (const note of notes) {
      const text = note.content.text ?? "";
      if (dirty[note.visibility] && drafts[note.visibility] === text) {
        setDirty((current) => ({ ...current, [note.visibility]: false }));
      } else if (!dirty[note.visibility] && drafts[note.visibility] !== text) {
        setDrafts((current) => ({ ...current, [note.visibility]: text }));
      }
    }
  }
  if (!isHost && visibility !== "all") {
    setVisibility("all");
  }

  const active = notes.find((note) => note.visibility === visibility) ?? null;
  const text = drafts[visibility];
  const isDirty = dirty[visibility];

  const tabs: { value: NoteVisibility; label: string }[] = [
    { value: "all", label: "Shared" },
    ...(isHost ? [{ value: "host_only" as NoteVisibility, label: "Host-only" }] : []),
  ];

  return (
    <aside aria-label="Notes" className={cn(PANEL_BASE, "min-h-0", className)}>
      <PanelHeader title="Notes" onClose={onClose} />

      <div role="tablist" aria-label="Notes documents" className="flex gap-1">
        {tabs.map((tab) => (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={visibility === tab.value}
            onClick={() => setVisibility(tab.value)}
            className={cn(
              "hover:bg-muted rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
              visibility === tab.value && "bg-muted",
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <Textarea
        aria-label={visibility === "all" ? "Shared notes" : "Host-only notes"}
        placeholder={
          connectionOpen ? "Start writing — everyone in the meet sees this." : "Connecting…"
        }
        value={text}
        onChange={(event) => {
          const next = event.target.value;
          setDrafts((current) => ({ ...current, [visibility]: next }));
          setDirty((current) => ({ ...current, [visibility]: true }));
        }}
        disabled={!connectionOpen}
        className="min-h-40 flex-1 resize-none"
      />

      {!connectionOpen ? (
        <Alert variant="warning">
          <AlertTitle>Reconnecting</AlertTitle>
          <AlertDescription>Notes will save again once the meet reconnects.</AlertDescription>
        </Alert>
      ) : null}

      <div className="flex items-center justify-between gap-3">
        <p className="text-muted-foreground truncate text-xs">
          {isDirty
            ? "Unsaved changes"
            : active?.updated_by_name
              ? `Saved by ${active.updated_by_name}`
              : "No notes yet"}
        </p>
        <Button
          size="sm"
          disabled={!isDirty || !connectionOpen}
          onClick={() => onSave?.(visibility, text)}
        >
          Save
        </Button>
      </div>
    </aside>
  );
}

export { ChatPanel, NotesPanel, PeoplePanel };
export type { PanelParticipant, ChatMessage };
