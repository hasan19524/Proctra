"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import {
  CalendarDaysIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  CircleHelpIcon,
  SettingsIcon,
  ShieldCheckIcon,
  VideoIcon,
} from "lucide-react";

import { RequireSession } from "@/components/auth/session-context";
import { UserMenu } from "@/components/auth/user-menu";
import { ThemeToggle } from "@/components/theme/theme-toggle";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { toast } from "@/components/ui/toast";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { extractMeetingCode, meetingsApi, type MeetingHistoryItem } from "@/lib/api";
import { cn } from "cn";

const NAV_ITEMS = [
  { label: "Meetings", icon: CalendarDaysIcon, href: "/" },
] as const;

const WEEKDAY_LABELS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];

function startOfWeek(date: Date): Date {
  const start = new Date(date);
  start.setDate(date.getDate() - ((date.getDay() + 6) % 7));
  return start;
}

export default function Home() {
  const router = useRouter();
  const [code, setCode] = React.useState("");
  const [isStarting, setIsStarting] = React.useState(false);
  const [recent, setRecent] = React.useState<MeetingHistoryItem[] | null>(null);
  const [createOpen, setCreateOpen] = React.useState(false);
  const today = React.useMemo(() => new Date(), []);

  React.useEffect(() => {
    let cancelled = false;
    meetingsApi
      .history(8)
      .then((items) => {
        if (!cancelled) setRecent(items);
      })
      .catch(() => {
        if (!cancelled) setRecent([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const week = React.useMemo(() => {
    const start = startOfWeek(today);
    return Array.from({ length: 7 }, (_, index) => {
      const day = new Date(start);
      day.setDate(start.getDate() + index);
      return day;
    });
  }, [today]);

  const dateLabel = today.toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
  });

  const startMeet = async (options?: {
    kind?: "standard" | "exam";
    title?: string;
    password?: string;
    waitingRoom?: boolean;
    inviteEmails?: string[];
  }) => {
    setIsStarting(true);
    try {
      const meeting = await meetingsApi.create({
        kind: options?.kind ?? "standard",
        title: options?.title,
        password: options?.password,
        waitingRoom: options?.waitingRoom,
        inviteEmails: options?.inviteEmails,
      });
      router.push(`/room/${meeting.code}`);
    } catch (error) {
      toast.add({
        type: "error",
        title: "Couldn't start a meet",
        description: error instanceof Error ? error.message : undefined,
      });
      setIsStarting(false);
    }
  };

  const joinMeet = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const extracted = extractMeetingCode(code);
    if (!extracted) {
      toast.add({
        type: "error",
        title: "That doesn't look like a meet code",
        description: "Codes look like abc-def-ghi — or paste the invite link.",
      });
      return;
    }
    router.push(`/room/${extracted}`);
  };

  return (
    <RequireSession>
      <div className="bg-background text-foreground flex h-svh flex-col">
        <header className="flex h-16 shrink-0 items-center gap-3 border-b px-3 sm:gap-4 sm:px-4">
          <Link href="/" className="flex shrink-0 items-center gap-2">
            <span
              aria-hidden="true"
              className="bg-primary text-primary-foreground flex size-9 items-center justify-center rounded-lg"
            >
              <VideoIcon />
            </span>
            <span className="font-heading hidden text-lg font-semibold tracking-tight sm:block">
              Procto
            </span>
          </Link>

          <form
            onSubmit={joinMeet}
            className="border-input bg-muted/60 focus-within:ring-ring/50 mx-auto flex w-full max-w-md items-center gap-2 rounded-full border py-1.5 pr-1.5 pl-4 focus-within:ring-3"
          >
            <Input
              aria-label="Enter a code or link"
              placeholder="Enter a code or link"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              className="h-8 flex-1 border-0 bg-transparent px-0 shadow-none focus-visible:ring-0"
            />
            <Button type="submit" size="sm" disabled={!code.trim()} className="rounded-full">
              Join
            </Button>
          </form>

          <div className="flex shrink-0 items-center gap-1">
            <Button
              variant="success"
              onClick={() => setCreateOpen(true)}
              disabled={isStarting}
              className="hidden rounded-full sm:flex"
            >
              {isStarting ? (
                <Spinner data-icon="inline-start" />
              ) : (
                <VideoIcon data-icon="inline-start" />
              )}
              New meet
            </Button>
            <Button variant="ghost" size="icon" aria-label="Help">
              <CircleHelpIcon />
            </Button>
            <Button variant="ghost" size="icon" aria-label="Settings" onClick={() => router.push("/settings")}>
              <SettingsIcon />
            </Button>
            <ThemeToggle />
            <UserMenu />
          </div>
        </header>

        <div className="flex min-h-0 flex-1">
          <nav
            aria-label="Primary"
            className="flex w-20 shrink-0 flex-col items-center gap-1 border-r pt-4 sm:w-24"
          >
            {NAV_ITEMS.map((item) => {
              const isActive = item.href === "/";
              return (
                <Link
                  key={item.label}
                  href={item.href}
                  aria-current={isActive ? "page" : undefined}
                  className={cn(
                    "focus-visible:ring-ring/50 flex w-full flex-col items-center gap-1 px-2 py-2 text-xs focus-visible:ring-3 focus-visible:outline-none",
                    isActive
                      ? "text-primary font-medium"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  <span
                    aria-hidden="true"
                    className={cn(
                      "flex size-10 items-center justify-center rounded-full transition-colors [&_svg]:size-5",
                      isActive ? "bg-primary/10" : "hover:bg-muted",
                    )}
                  >
                    <item.icon />
                  </span>
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <main className="flex min-w-0 flex-1 flex-col overflow-y-auto px-4 py-6 sm:px-8">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <Button variant="ghost" size="icon" aria-label="Previous week">
                  <ChevronLeftIcon />
                </Button>
                <h1
                  className="font-heading text-xl font-medium sm:text-2xl"
                  suppressHydrationWarning
                >
                  {dateLabel}
                </h1>
                <Button variant="ghost" size="icon" aria-label="Next week">
                  <ChevronRightIcon />
                </Button>
              </div>

              <div className="flex items-center gap-1">
                {week.map((day, index) => {
                  const isToday = day.toDateString() === today.toDateString();
                  return (
                    <div
                      key={day.toISOString()}
                      className="flex w-10 flex-col items-center gap-1.5"
                    >
                      <span className="text-muted-foreground text-xs">{WEEKDAY_LABELS[index]}</span>
                      <span
                        className={cn(
                          "flex size-8 items-center justify-center rounded-full text-sm tabular-nums",
                          isToday && "bg-primary text-primary-foreground font-medium",
                        )}
                      >
                        {day.getDate()}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            <section className="flex flex-1 flex-col py-6">
              {recent && recent.length > 0 ? (
                <div className="flex flex-col gap-3">
                  <h2 className="font-heading text-sm font-medium text-muted-foreground">
                    Recent
                  </h2>
                  <ul className="flex flex-col gap-2">
                    {recent.map((item) => (
                      <li key={item.code}>
                        <Link
                          href={`/room/${item.code}`}
                          className="bg-card text-card-foreground hover:bg-accent flex items-center gap-3 rounded-xl border px-4 py-3 transition-colors"
                        >
                          <span
                            aria-hidden="true"
                            className="bg-primary/10 text-primary flex size-9 shrink-0 items-center justify-center rounded-lg"
                          >
                            <VideoIcon />
                          </span>
                          <span className="flex min-w-0 flex-1 flex-col">
                            <span className="truncate font-medium">
                              {item.title || "Untitled meet"}
                            </span>
                            <span className="text-muted-foreground truncate text-xs">
                              {item.code} · {new Date(item.created_at).toLocaleString()}
                            </span>
                          </span>
                          <span
                            className={cn(
                              "shrink-0 rounded-full px-2.5 py-1 text-xs font-medium",
                              item.status === "ended"
                                ? "bg-muted text-muted-foreground"
                                : "bg-success/15 text-success",
                            )}
                          >
                            {item.status === "ended" ? "Ended" : "Live"}
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <Empty className="border-none shadow-none">
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <VideoIcon />
                    </EmptyMedia>
                    <EmptyTitle>No meetings yet</EmptyTitle>
                    <EmptyDescription>
                      Start a meet now, or enter a code to join one that is already running.
                    </EmptyDescription>
                  </EmptyHeader>

                  <Button
                    variant="success"
                    onClick={() => setCreateOpen(true)}
                    disabled={isStarting}
                    className="mt-4 rounded-full"
                  >
                    {isStarting ? (
                      <Spinner data-icon="inline-start" />
                    ) : (
                      <VideoIcon data-icon="inline-start" />
                    )}
                    New meet
                  </Button>
                </Empty>
              )}
            </section>
          </main>
        </div>

        <CreateMeetingDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          isStarting={isStarting}
          onStart={(options) => {
            setCreateOpen(false);
            void startMeet(options);
          }}
        />
      </div>
    </RequireSession>
  );
}

interface CreateMeetingDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  isStarting: boolean;
  onStart: (options: { kind: "standard" | "exam"; title?: string; password?: string; waitingRoom?: boolean; inviteEmails?: string[] }) => void;
}

/**
 * Create-meeting dialog (Phase 16): choose Standard or Exam mode.
 *
 * Exam mode requires a password, enables AI proctoring, and seeds the
 * invite roster the report's present/absent columns are graded against.
 */
function CreateMeetingDialog({ open, onOpenChange, isStarting, onStart }: CreateMeetingDialogProps) {
  const [kind, setKind] = React.useState<"standard" | "exam">("standard");
  const [title, setTitle] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [waitingRoom, setWaitingRoom] = React.useState(false);
  const [inviteEmails, setInviteEmails] = React.useState("");

  const canSubmit =
    !isStarting &&
    title.trim().length <= 120 &&
    // Exam meetings require a password (enforced server-side too).
    (kind !== "exam" || password.trim().length >= 8);

  const submit = () => {
    if (!canSubmit) return;
    const emails = inviteEmails
      .split(/[\n,]/)
      .map((s) => s.trim())
      .filter(Boolean);
    onStart({
      kind,
      title: title.trim() || undefined,
      password: kind === "exam" ? password.trim() : password.trim() || undefined,
      waitingRoom,
      inviteEmails: emails.length > 0 ? emails : undefined,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>New meeting</DialogTitle>
          <DialogDescription>
            Choose a standard meeting or a proctored exam room.
          </DialogDescription>
        </DialogHeader>

        {/* Kind switcher */}
        <div className="grid grid-cols-2 gap-3">
          <button
            type="button"
            onClick={() => setKind("standard")}
            className={cn(
              "flex flex-col items-start gap-1.5 rounded-xl border p-4 text-left transition-colors",
              kind === "standard"
                ? "border-primary bg-primary/5 ring-primary/30 ring-2"
                : "border-border hover:bg-muted/50",
            )}
          >
            <VideoIcon className="size-5" aria-hidden="true" />
            <span className="text-sm font-medium">Standard</span>
            <span className="text-muted-foreground text-xs">
              Regular meeting with chat, reactions, and screen share.
            </span>
          </button>
          <button
            type="button"
            onClick={() => setKind("exam")}
            className={cn(
              "flex flex-col items-start gap-1.5 rounded-xl border p-4 text-left transition-colors",
              kind === "exam"
                ? "border-warning bg-warning/5 ring-warning/30 ring-2"
                : "border-border hover:bg-muted/50",
            )}
          >
            <ShieldCheckIcon className="text-warning size-5" aria-hidden="true" />
            <span className="text-sm font-medium">Exam</span>
            <span className="text-muted-foreground text-xs">
              Proctored exam with password, AI integrity checks, and a downloadable report.
            </span>
          </button>
        </div>

        <div className="flex flex-col gap-3">
          <Input
            aria-label="Meeting title"
            placeholder="Meeting title (optional)"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            maxLength={120}
          />

          {kind === "exam" ? (
            <>
              <Input
                type="password"
                aria-label="Exam password"
                placeholder="Exam password (min 8 characters)"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="new-password"
                required
              />
              <textarea
                aria-label="Invite student emails"
                placeholder={"Invite students (one email per line)\nstudent1@school.edu\nstudent2@school.edu"}
                value={inviteEmails}
                onChange={(event) => setInviteEmails(event.target.value)}
                rows={3}
                className="border-input bg-background ring-offset-background placeholder:text-muted-foreground focus-visible:ring-ring/50 flex w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:outline-none"
              />
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={waitingRoom}
                  onChange={(event) => setWaitingRoom(event.target.checked)}
                  className="accent-primary size-4"
                />
                Apply to join (waiting room)
              </label>
              <p className="text-muted-foreground flex items-start gap-1.5 text-xs">
                <ShieldCheckIcon className="mt-0.5 size-3.5 shrink-0 text-warning" aria-hidden="true" />
                AI proctoring will run in each student&apos;s browser. Only signal labels
                (e.g. &ldquo;looking away +2&rdquo;) are sent to you — never their video.
              </p>
            </>
          ) : (
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={waitingRoom}
                onChange={(event) => setWaitingRoom(event.target.checked)}
                className="accent-primary size-4"
              />
              Apply to join (waiting room)
            </label>
          )}
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isStarting}>
            Cancel
          </Button>
          <Button variant="success" onClick={submit} disabled={!canSubmit}>
            {isStarting ? <Spinner data-icon="inline-start" /> : null}
            {kind === "exam" ? "Create exam" : "Create meeting"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
