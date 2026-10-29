"use client";

import * as React from "react";
import { usePathname, useRouter } from "next/navigation";

import { Spinner } from "@/components/ui/spinner";
import {
  authApi,
  refreshSession,
  type AuthResponse,
  type RegisterInput,
  type User,
} from "@/lib/api";

export type SessionStatus = "loading" | "authenticated" | "unauthenticated";

export interface SessionValue {
  status: SessionStatus;
  user: User | null;
  login: (email: string, password: string) => Promise<AuthResponse>;
  register: (input: RegisterInput) => Promise<AuthResponse>;
  logout: () => Promise<void>;
}

const SessionContext = React.createContext<SessionValue | null>(null);

export function useSession(): SessionValue {
  const value = React.useContext(SessionContext);
  if (!value) {
    throw new Error("useSession must be used within a SessionProvider");
  }
  return value;
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = React.useState<SessionStatus>("loading");
  const [user, setUser] = React.useState<User | null>(null);

  React.useEffect(() => {
    let active = true;
    // Safety net: if the session check never settles (network stall), leave the
    // spinner state so RequireSession can redirect to /login instead of hanging.
    const stallTimer = window.setTimeout(() => {
      if (active) {
        setUser(null);
        setStatus("unauthenticated");
      }
    }, 12_000);

    refreshSession()
      .then((auth) => {
        if (!active) return;
        setUser(auth.user);
        setStatus("authenticated");
      })
      .catch(() => {
        if (!active) return;
        setUser(null);
        setStatus("unauthenticated");
      })
      .finally(() => {
        window.clearTimeout(stallTimer);
      });
    return () => {
      active = false;
      window.clearTimeout(stallTimer);
    };
  }, []);

  const login = React.useCallback(async (email: string, password: string) => {
    const auth = await authApi.login(email, password);
    setUser(auth.user);
    setStatus("authenticated");
    return auth;
  }, []);

  const register = React.useCallback(async (input: RegisterInput) => {
    const auth = await authApi.register(input);
    setUser(auth.user);
    setStatus("authenticated");
    return auth;
  }, []);

  const logout = React.useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      setUser(null);
      setStatus("unauthenticated");
    }
  }, []);

  const value = React.useMemo(
    () => ({ status, user, login, register, logout }),
    [status, user, login, register, logout],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

/**
 * Redirects to /login once the session is known to be missing.
 * Returns the current status so callers can render a loading state meanwhile.
 */
export function useRequireSession(): SessionStatus {
  const { status } = useSession();
  const router = useRouter();
  const pathname = usePathname();

  React.useEffect(() => {
    if (status === "unauthenticated") {
      // Preserve the destination (e.g. an invite link /room/abc-def-ghi) so
      // login can return the visitor straight to the meeting.
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [status, router, pathname]);

  return status;
}

/** Renders a full-screen loading state until the session is authenticated. */
export function RequireSession({ children }: { children: React.ReactNode }) {
  const status = useRequireSession();

  if (status !== "authenticated") {
    return (
      <div
        role="status"
        aria-label="Checking session"
        className="bg-background text-foreground flex h-svh items-center justify-center"
      >
        <Spinner className="size-6" />
      </div>
    );
  }

  return <>{children}</>;
}
