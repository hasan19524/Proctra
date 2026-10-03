"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import {
  CalendarDaysIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  CircleHelpIcon,
  GraduationCapIcon,
  PaletteIcon,
  SettingsIcon,
  VideoIcon,
} from "lucide-react";

import { RequireSession } from "@/components/auth/session-context";
import { UserMenu } from "@/components/auth/user-menu";
import { ThemeToggle } from "@/components/theme/theme-toggle";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { cn } from "cn";

const NAV_ITEMS = [
  { label: "Meetings", icon: CalendarDaysIcon, href: "/" },
  { label: "Exams", icon: GraduationCapIcon, href: "#exams" },
  { label: "Design", icon: PaletteIcon, href: "/design" },
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
  const today = React.useMemo(() => new Date(), []);

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

  const goRoom = () => router.push("/room");

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
            onSubmit={(event) => {
              event.preventDefault();
              if (code.trim()) goRoom();
            }}
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
              render={<Link href="/room" />}
              variant="success"
              className="hidden rounded-full sm:flex"
            >
              <VideoIcon data-icon="inline-start" />
              New meet
            </Button>
            <Button variant="ghost" size="icon" aria-label="Help">
              <CircleHelpIcon />
            </Button>
            <Button variant="ghost" size="icon" aria-label="Settings">
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

            <section className="flex flex-1 flex-col items-center justify-center py-10">
              <Empty className="border-none shadow-none">
                <EmptyHeader>
                  <EmptyMedia variant="icon">
                    <VideoIcon />
                  </EmptyMedia>
                  <EmptyTitle>No meetings scheduled for today</EmptyTitle>
                  <EmptyDescription>
                    Start a meet now, or enter a code to join one that is already running.
                  </EmptyDescription>
                </EmptyHeader>
                <Button
                  render={<Link href="/room" />}
                  variant="success"
                  className="mt-4 rounded-full"
                >
                  <VideoIcon data-icon="inline-start" />
                  New meet
                </Button>
              </Empty>
            </section>
          </main>
        </div>
      </div>
    </RequireSession>
  );
}
