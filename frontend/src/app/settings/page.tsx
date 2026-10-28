"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { ArrowLeftIcon, BellIcon, ShieldIcon, SunIcon } from "lucide-react";

import { RequireSession } from "@/components/auth/session-context";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ThemeToggle } from "@/components/theme/theme-toggle";

export default function SettingsPage() {
  const router = useRouter();

  return (
    <RequireSession>
      <main className="bg-background text-foreground flex min-h-svh flex-col">
        <header className="flex h-16 shrink-0 items-center gap-3 border-b px-3 sm:gap-4 sm:px-4">
          <button
            type="button"
            onClick={() => router.push("/")}
            aria-label="Back to home"
            className="flex shrink-0 items-center gap-2"
          >
            <span
              aria-hidden="true"
              className="bg-primary text-primary-foreground flex size-9 items-center justify-center rounded-lg"
            >
              <ArrowLeftIcon />
            </span>
            <span className="font-heading hidden text-lg font-semibold tracking-tight sm:block">
              Procto
            </span>
          </button>
          <span className="font-heading ml-2 text-lg font-semibold tracking-tight">Settings</span>
        </header>

        <div className="flex flex-1 items-start justify-center px-4 py-10">
          <div className="flex w-full max-w-md flex-col gap-4">
            <Card>
              <CardHeader>
                <CardTitle>Appearance</CardTitle>
                <CardDescription>Choose how Procto looks.</CardDescription>
              </CardHeader>
              <CardContent className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <SunIcon className="text-muted-foreground size-4" aria-hidden="true" />
                  <span className="text-sm">Color theme</span>
                </div>
                <ThemeToggle />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Notifications</CardTitle>
                <CardDescription>Manage meeting alerts.</CardDescription>
              </CardHeader>
              <CardContent className="text-muted-foreground flex flex-col gap-3 text-sm">
                <div className="flex items-center gap-3">
                  <BellIcon className="size-4 shrink-0" aria-hidden="true" />
                  <span>In-meeting chat notifications</span>
                  <span className="ml-auto text-xs">On</span>
                </div>
                <div className="flex items-center gap-3">
                  <BellIcon className="size-4 shrink-0" aria-hidden="true" />
                  <span>Meeting reminders</span>
                  <span className="ml-auto text-xs">On</span>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Privacy &amp; security</CardTitle>
                <CardDescription>How your data is handled.</CardDescription>
              </CardHeader>
              <CardContent className="text-muted-foreground flex flex-col gap-3 text-sm">
                <div className="flex items-center gap-3">
                  <ShieldIcon className="size-4 shrink-0" aria-hidden="true" />
                  <span>Meeting passwords &amp; waiting room</span>
                  <span className="ml-auto text-xs">Enabled</span>
                </div>
                <div className="flex items-center gap-3">
                  <ShieldIcon className="size-4 shrink-0" aria-hidden="true" />
                  <span>Audit logging</span>
                  <span className="ml-auto text-xs">Enabled</span>
                </div>
              </CardContent>
            </Card>

            <p className="text-muted-foreground mt-2 text-center text-xs">
              <Link href="/" className="text-primary font-medium hover:underline">
                Back to home
              </Link>
            </p>
          </div>
        </div>
      </main>
    </RequireSession>
  );
}
