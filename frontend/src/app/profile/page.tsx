"use client";

import * as React from "react";
import Link from "next/link";

import { UserIcon, ArrowLeftIcon, LogOutIcon, MailIcon, ShieldIcon } from "lucide-react";

import { RequireSession, useSession } from "@/components/auth/session-context";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";

export default function ProfilePage() {
  const { user, logout } = useSession();
  const [pending, setPending] = React.useState(false);

  const handleLogout = async () => {
    setPending(true);
    try {
      await logout();
    } finally {
      setPending(false);
    }
  };

  return (
    <RequireSession>
      <main className="bg-background text-foreground flex min-h-svh flex-col">
        <header className="flex h-16 shrink-0 items-center gap-3 border-b px-3 sm:gap-4 sm:px-4">
          <Link href="/" aria-label="Back to home" className="flex shrink-0 items-center gap-2">
            <span
              aria-hidden="true"
              className="bg-primary text-primary-foreground flex size-9 items-center justify-center rounded-lg"
            >
              <ArrowLeftIcon />
            </span>
            <span className="font-heading hidden text-lg font-semibold tracking-tight sm:block">
              Procto
            </span>
          </Link>
          <span className="font-heading ml-2 text-lg font-semibold tracking-tight">Profile</span>
        </header>

        <div className="flex flex-1 items-start justify-center px-4 py-10">
          <div className="w-full max-w-md">
            <Card>
              <CardHeader>
                <CardTitle>Account</CardTitle>
                <CardDescription>Your Procto profile and session.</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <div className="flex items-center gap-4">
                  <span
                    aria-hidden="true"
                    className="bg-primary/10 text-primary flex size-14 items-center justify-center rounded-full text-lg font-semibold"
                  >
                    {user?.display_name?.charAt(0).toUpperCase() ?? "?"}
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-base font-semibold">{user?.display_name}</p>
                    <p className="text-muted-foreground truncate text-sm">{user?.email}</p>
                  </div>
                </div>

                <div className="flex flex-col gap-3 border-t pt-4">
                  <div className="flex items-center gap-3 text-sm">
                    <MailIcon
                      className="text-muted-foreground size-4 shrink-0"
                      aria-hidden="true"
                    />
                    <span className="text-muted-foreground">Email</span>
                    <span className="ml-auto truncate font-medium">{user?.email}</span>
                  </div>
                  <div className="flex items-center gap-3 text-sm">
                    <ShieldIcon
                      className="text-muted-foreground size-4 shrink-0"
                      aria-hidden="true"
                    />
                    <span className="text-muted-foreground">Role</span>
                    <span className="ml-auto font-medium capitalize">{user?.role}</span>
                  </div>
                  <div className="flex items-center gap-3 text-sm">
                    <UserIcon
                      className="text-muted-foreground size-4 shrink-0"
                      aria-hidden="true"
                    />
                    <span className="text-muted-foreground">Member since</span>
                    <span className="ml-auto font-medium">
                      {user?.created_at ? new Date(user.created_at).toLocaleDateString() : "—"}
                    </span>
                  </div>
                </div>

                <Button
                  variant="outline"
                  className="mt-2 w-full"
                  onClick={() => void handleLogout()}
                  disabled={pending}
                >
                  {pending ? (
                    <Spinner data-icon="inline-start" />
                  ) : (
                    <LogOutIcon data-icon="inline-start" />
                  )}
                  Sign out
                </Button>
              </CardContent>
            </Card>

            <p className="text-muted-foreground mt-4 text-center text-xs">
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
