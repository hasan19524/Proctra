"use client";

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";

import { ApiError, meetingsApi, type Meeting } from "@/lib/api";
import { RequireSession, useSession } from "@/components/auth/session-context";
import { InCallSession } from "@/components/meeting/in-call-session";
import { PreJoinLobby, type JoinOptions } from "@/components/meeting/prejoin-lobby";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";

interface RoomParams {
  code: string;
}

function CenteredStatus({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="bg-background text-foreground flex h-svh flex-col items-center justify-center gap-3 px-4 text-center">
      <h1 className="font-heading text-xl font-semibold">{title}</h1>
      <p className="text-muted-foreground max-w-md text-sm">{description}</p>
      {action}
    </div>
  );
}

function RoomGate({ code }: RoomParams) {
  const router = useRouter();
  const { user } = useSession();

  const [meeting, setMeeting] = React.useState<Meeting | null>(null);
  const [error, setError] = React.useState<ApiError | null>(null);
  const [join, setJoin] = React.useState<JoinOptions | null>(null);

  React.useEffect(() => {
    let active = true;
    meetingsApi
      .get(code)
      .then((found) => {
        if (active) setMeeting(found);
      })
      .catch((err: unknown) => {
        if (active && err instanceof ApiError) setError(err);
      });
    return () => {
      active = false;
    };
  }, [code]);

  if (error) {
    if (error.status === 404) {
      return (
        <CenteredStatus
          title="Meeting not found"
          description={`No meet matches the code ${code}. Check the code and try again.`}
          action={
            <Button render={<Link href="/" />} variant="outline" className="mt-2 rounded-full">
              Back to home
            </Button>
          }
        />
      );
    }
    return (
      <CenteredStatus
        title="Something went wrong"
        description={error.message}
        action={
          <Button render={<Link href="/" />} variant="outline" className="mt-2 rounded-full">
            Back to home
          </Button>
        }
      />
    );
  }

  if (!meeting || !user) {
    return (
      <div
        role="status"
        aria-label="Loading meeting"
        className="bg-background text-foreground flex h-svh items-center justify-center"
      >
        <Spinner className="size-6" />
      </div>
    );
  }

  if (meeting.status === "ended") {
    return (
      <CenteredStatus
        title="This meet has ended"
        description={`The meet ${meeting.code} is no longer running.`}
        action={
          <Button render={<Link href="/" />} variant="outline" className="mt-2 rounded-full">
            Back to home
          </Button>
        }
      />
    );
  }

  if (!join) {
    return (
      <PreJoinLobby
        code={meeting.code}
        title={meeting.title}
        defaultName={user.display_name}
        onJoin={setJoin}
      />
    );
  }

  return (
    <InCallSession
      code={meeting.code}
      displayName={join.displayName}
      micOn={join.micOn}
      cameraOn={join.cameraOn}
      password={join.password}
      onLeave={() => router.push("/")}
    />
  );
}

function LoadingScreen() {
  return (
    <div
      role="status"
      aria-label="Loading meeting"
      className="bg-background text-foreground flex h-svh items-center justify-center"
    >
      <Spinner className="size-6" />
    </div>
  );
}

export default function RoomPage() {
  const params = useParams<{ code: string }>();
  const code = (params?.code ?? "").toLowerCase();

  if (!code) {
    return <LoadingScreen />;
  }

  return (
    <RequireSession>
      <RoomGate code={code} />
    </RequireSession>
  );
}
