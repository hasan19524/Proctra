// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { Track } from "livekit-client";

import { FloatingReactions, InCallView } from "@/components/meeting/in-call-view";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { MediaTile } from "@/hooks/use-livekit-room";
import type { WsParticipant, WsReaction } from "@/hooks/use-meeting-ws";

afterEach(cleanup);

function renderView(overrides: Partial<Parameters<typeof InCallView>[0]> = {}) {
  const props = {
    code: "ktq-vxm-pnz",
    displayName: "Hasan",
    participants: [],
    selfUserId: null,
    connection: "open" as const,
    messages: [],
    meeting: null,
    notes: [],
    reactions: [],
    onSendChat: vi.fn(() => "frame-1"),
    onSendNote: vi.fn(() => "frame-2"),
    onSendReaction: vi.fn(() => "frame-3"),
    onHostAction: vi.fn(),
    micOn: true,
    cameraOn: true,
    isHandRaised: false,
    onToggleHand: vi.fn(),
    onToggleMic: vi.fn(),
    onToggleCamera: vi.fn(),
    onLeave: vi.fn(),
    ...overrides,
  };
  render(
    <TooltipProvider>
      <InCallView {...props} />
    </TooltipProvider>,
  );
  return props;
}

describe("InCallView", () => {
  it("waits for others in an empty room", () => {
    renderView();
    expect(screen.getByText(/Waiting for others to join/)).toBeTruthy();
  });

  it("toggles the hand through the controlled handler", () => {
    const onToggleHand = vi.fn();
    renderView({ onToggleHand });

    fireEvent.click(screen.getByRole("button", { name: "Raise hand (R)" }));
    expect(onToggleHand).toHaveBeenCalledTimes(1);
  });

  it("sends a reaction through the socket handler", () => {
    const onSendReaction = vi.fn(() => "frame-3");
    renderView({ onSendReaction });

    fireEvent.click(screen.getByRole("button", { name: "Send a reaction" }));
    fireEvent.click(screen.getByRole("button", { name: "React with Party" }));

    expect(onSendReaction).toHaveBeenCalledWith("Party");
  });

  it("renders floating reactions with emoji and sender name", () => {
    const reactions: WsReaction[] = [
      { id: 1, user_id: "u2", name: "Amina Yusuf", label: "Party", at: Date.now() },
    ];
    renderView({ reactions });

    expect(screen.getByLabelText("Reactions")).toBeTruthy();
    expect(screen.getByText("Amina Yusuf")).toBeTruthy();
  });

  it("toggles screen share through the controlled handler", () => {
    const onToggleScreenShare = vi.fn();
    renderView({ onToggleScreenShare });

    fireEvent.click(screen.getByRole("button", { name: "Share screen (S)" }));
    expect(onToggleScreenShare).toHaveBeenCalledTimes(1);
  });

  it("blocks screen sharing when the host disabled it", () => {
    const onToggleScreenShare = vi.fn();
    renderView({ canScreenShare: false, onToggleScreenShare });

    fireEvent.click(screen.getByRole("button", { name: "Share screen (S)" }));
    expect(onToggleScreenShare).not.toHaveBeenCalled();
  });

  it("promotes a presenter's screen to the stage and keeps cameras in the strip", () => {
    const fakeTrack = { attach: vi.fn(), detach: vi.fn() } as unknown as Track;
    const participants: WsParticipant[] = [
      {
        user_id: "u1",
        name: "Hasan",
        is_host: true,
        mic_on: true,
        camera_on: true,
        hand_raised: false,
        screen_share_on: false,
      },
      {
        user_id: "u2",
        name: "Amina Yusuf",
        is_host: false,
        mic_on: true,
        camera_on: true,
        hand_raised: false,
        screen_share_on: true,
      },
    ];
    const mediaTiles: MediaTile[] = [
      { id: "u2", name: "Amina Yusuf", isLocal: false, screenTrack: fakeTrack },
    ];
    renderView({ participants, selfUserId: "u1", mediaTiles, isScreenSharing: false });

    expect(screen.getByText("Amina Yusuf is presenting")).toBeTruthy();
    expect(fakeTrack.attach).toHaveBeenCalled();
    // Your own camera moves into the strip while someone else presents.
    expect(screen.getByText("Hasan (You)")).toBeTruthy();
    expect(screen.getByText("Sharing screen")).toBeTruthy();
  });
});

describe("FloatingReactions", () => {
  it("hides when empty and renders every active reaction", () => {
    const { rerender } = render(<FloatingReactions reactions={[]} />);
    expect(screen.queryByLabelText("Reactions")).toBeNull();

    // The float animation fades items out in CSS; the hook prunes them.
    rerender(
      <FloatingReactions
        reactions={[{ id: 2, user_id: "u3", name: "Fresh", label: "Clap", at: Date.now() }]}
      />,
    );
    expect(screen.getByText("Fresh")).toBeTruthy();
  });
});
