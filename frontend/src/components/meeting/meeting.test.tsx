// @vitest-environment jsdom
import * as React from "react";

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { MeetingControls } from "@/components/meeting/meeting-controls";
import {
  MeetingEmptyState,
  MeetingErrorState,
  MeetingLoadingState,
} from "@/components/meeting/meeting-states";
import { ParticipantTile } from "@/components/meeting/participant-tile";
import {
  ConnectionQuality,
  LiveIndicator,
  StatusIndicator,
} from "@/components/meeting/status-indicator";
import { TooltipProvider } from "@/components/ui/tooltip";

afterEach(cleanup);

describe("StatusIndicator", () => {
  it("renders a text label for every meeting status", () => {
    const cases = [
      ["connecting", "Connecting"],
      ["connected", "Connected"],
      ["reconnecting", "Reconnecting"],
      ["failed", "Connection lost"],
    ] as const;

    for (const [status, label] of cases) {
      render(<StatusIndicator status={status} />);
      expect(screen.getByText(label)).toBeTruthy();
      cleanup();
    }
  });

  it("announces connection quality to assistive tech", () => {
    render(<ConnectionQuality quality="poor" showLabel={false} />);
    const status = screen.getByRole("status");
    expect(status.getAttribute("aria-label")).toBe("Poor connection");
  });

  it("renders a live badge", () => {
    render(<LiveIndicator />);
    expect(screen.getByText("Live")).toBeTruthy();
  });
});

describe("ParticipantTile", () => {
  it("labels the tile after the participant", () => {
    render(<ParticipantTile name="Amina Yusuf" />);
    expect(screen.getByRole("group", { name: "Amina Yusuf's video" })).toBeTruthy();
    expect(screen.getAllByText("AY").length).toBeGreaterThan(0);
  });

  it("surfaces mute, camera and host state with text, not color alone", () => {
    render(<ParticipantTile name="Priya Nair" isMuted isCameraOff isHost isHandRaised />);

    expect(screen.getByLabelText("Priya Nair is muted")).toBeTruthy();
    expect(screen.getByText("Camera off")).toBeTruthy();
    expect(screen.getByText("Host")).toBeTruthy();
    expect(screen.getByText("Hand")).toBeTruthy();
  });

  it("marks the speaking state on the tile surface", () => {
    const { container } = render(<ParticipantTile name="Carlos Mendes" isSpeaking />);
    expect(container.querySelector('[data-speaking="true"]')).toBeTruthy();
    expect(container.querySelector(".ring-2")).toBeTruthy();
  });

  it("derives initials from the full name", () => {
    render(<ParticipantTile name="omar haddad" />);
    expect(screen.getAllByText("OH").length).toBeGreaterThan(0);
  });
});

describe("MeetingControls", () => {
  const baseState = {
    isMicOn: true,
    isCameraOn: true,
    isScreenSharing: false,
    isHandRaised: false,
  };

  function renderControls(overrides: Partial<React.ComponentProps<typeof MeetingControls>> = {}) {
    return render(
      <TooltipProvider>
        <MeetingControls
          state={baseState}
          onToggleMic={vi.fn()}
          onToggleCamera={vi.fn()}
          onToggleScreenShare={vi.fn()}
          onToggleHand={vi.fn()}
          onOpenChat={vi.fn()}
          onToggleReactions={vi.fn()}
          onLeave={vi.fn()}
          {...overrides}
        />
      </TooltipProvider>,
    );
  }

  it("renders a labelled toolbar with one labelled control each", () => {
    renderControls();

    expect(screen.getByRole("toolbar", { name: "Meeting controls" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Turn off microphone (M)" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Turn off camera (V)" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Share screen (S)" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Send a reaction" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Chat (C)" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Raise hand (R)" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "More options" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Leave meeting" })).toBeTruthy();
  });

  it("exposes toggle state through aria-pressed", () => {
    renderControls();
    expect(
      screen.getByRole("button", { name: "Turn off microphone (M)" }).getAttribute("aria-pressed"),
    ).toBe("true");
    expect(
      screen.getByRole("button", { name: "Share screen (S)" }).getAttribute("aria-pressed"),
    ).toBe("false");
  });

  it("calls handlers when controls are clicked", () => {
    const onToggleMic = vi.fn();
    const onLeave = vi.fn();
    const onOpenChat = vi.fn();
    const onToggleReactions = vi.fn();
    renderControls({ onToggleMic, onLeave, onOpenChat, onToggleReactions });

    fireEvent.click(screen.getByRole("button", { name: "Turn off microphone (M)" }));
    fireEvent.click(screen.getByRole("button", { name: "Chat (C)" }));
    fireEvent.click(screen.getByRole("button", { name: "Send a reaction" }));
    fireEvent.click(screen.getByRole("button", { name: "Leave meeting" }));

    expect(onToggleMic).toHaveBeenCalledTimes(1);
    expect(onOpenChat).toHaveBeenCalledTimes(1);
    expect(onToggleReactions).toHaveBeenCalledTimes(1);
    expect(onLeave).toHaveBeenCalledTimes(1);
  });

  it("flips labels when mic and camera are off", () => {
    renderControls({ state: { ...baseState, isMicOn: false, isCameraOn: false } });
    expect(screen.getByRole("button", { name: "Turn on microphone (M)" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Turn on camera (V)" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Turn off microphone (M)" })).toBeNull();
  });

  it("disables controls while busy and while leaving", () => {
    renderControls({ isBusy: true, isLeaving: true });
    const mic = screen.getByRole("button", { name: "Turn off microphone (M)" });
    const leave = screen.getByRole("button", { name: "Leaving meeting" });
    expect(mic.hasAttribute("disabled")).toBe(true);
    expect(leave.hasAttribute("disabled")).toBe(true);
  });
});

describe("Meeting states", () => {
  it("loading state is announced as busy and shows skeletons", () => {
    const { container } = render(<MeetingLoadingState />);
    expect(screen.getByText("Connecting to meet…")).toBeTruthy();
    expect(container.querySelector('[aria-busy="true"]')).toBeTruthy();
    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
  });

  it("error state is an alert with a working retry", () => {
    const onRetry = vi.fn();
    render(<MeetingErrorState onRetry={onRetry} />);

    expect(screen.getByRole("alert")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("error state renders without retry when no handler is given", () => {
    render(<MeetingErrorState />);
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /retry/i })).toBeNull();
  });

  it("empty state offers an invite action", () => {
    const onAction = vi.fn();
    render(<MeetingEmptyState onAction={onAction} />);

    expect(screen.getByText("No one else is here yet")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /copy invite link/i }));
    expect(onAction).toHaveBeenCalledTimes(1);
  });
});
