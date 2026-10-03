"use client";

import * as React from "react";
import { useRouter } from "next/navigation";

import { LogOutIcon } from "lucide-react";

import { useSession } from "@/components/auth/session-context";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  const first = parts[0]?.charAt(0) ?? "";
  const second = parts.length > 1 ? (parts[parts.length - 1]?.charAt(0) ?? "") : "";
  return (first + second).toUpperCase() || "?";
}

/** Account menu shown in headers: initials avatar + sign out. */
export function UserMenu() {
  const router = useRouter();
  const { status, user, logout } = useSession();

  const onSignOut = async () => {
    try {
      await logout();
    } catch {
      // Local session state is already cleared; navigate regardless.
    }
    router.replace("/login");
  };

  if (status !== "authenticated" || !user) {
    return (
      <span aria-hidden="true" className="bg-muted inline-flex size-9 animate-pulse rounded-full" />
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button variant="ghost" size="icon" aria-label="Account menu" className="rounded-full">
            <span
              aria-hidden="true"
              className="bg-accent text-primary-foreground ring-primary/40 flex size-9 items-center justify-center rounded-full text-sm font-medium ring-2"
            >
              {initialsOf(user.display_name)}
            </span>
          </Button>
        }
      />
      <DropdownMenuContent align="end" className="min-w-56">
        <DropdownMenuLabel className="flex flex-col gap-0.5">
          <span className="text-sm font-medium">{user.display_name}</span>
          <span className="text-muted-foreground text-xs font-normal">{user.email}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => void onSignOut()}>
          <LogOutIcon data-icon="inline-start" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
