// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { FloatingReactions, InCallView } from "@/components/meeting/in-call-view";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { WsReaction } from "@/hooks/use-meeting-ws";

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
