// @vitest-environment jsdom
import * as React from "react";

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { MeetingTopBar } from "@/components/meeting/meeting-top-bar";
import { ChatPanel, PeoplePanel } from "@/components/meeting/meeting-panels";
import { ReactionBar } from "@/components/meeting/reaction-bar";
import { UtilityCluster } from "@/components/meeting/meeting-controls";
import { TooltipProvider } from "@/components/ui/tooltip";

afterEach(cleanup);

describe("MeetingTopBar", () => {
  it("shows time, meet code and participant count", () => {
    render(<MeetingTopBar code="ktq-vxm-pnz" time="10:24" participantCount={4} />);

    expect(screen.getByText("10:24")).toBeTruthy();
    expect(screen.getByText("ktq-vxm-pnz")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Show people, 4 in this meet" })).toBeTruthy();
  });

  it("fires handlers for details and people", () => {
    const onShowDetails = vi.fn();
    const onOpenPeople = vi.fn();
    render(
      <MeetingTopBar
        code="ktq-vxm-pnz"
        time="10:24"
        participantCount={2}
        onShowDetails={onShowDetails}
        onOpenPeople={onOpenPeople}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Meeting details" }));
    fireEvent.click(screen.getByRole("button", { name: "Show people, 2 in this meet" }));

    expect(onShowDetails).toHaveBeenCalledTimes(1);
    expect(onOpenPeople).toHaveBeenCalledTimes(1);
  });
});

describe("PeoplePanel", () => {
  const participants = [
    { id: "you", name: "Hasan", role: "Meeting host", isYou: true },
    { id: "amina", name: "Amina Yusuf", role: "Contributor" },
    { id: "carlos", name: "Carlos Mendes", role: "Contributor", isMuted: true },
  ];

  it("lists participants with roles and mute state", () => {
    render(<PeoplePanel participants={participants} />);

    expect(screen.getByText("Hasan")).toBeTruthy();
    expect(screen.getByText("(You)")).toBeTruthy();
    expect(screen.getByText("Meeting host")).toBeTruthy();
    expect(screen.getAllByText("Contributor").length).toBe(2);
    expect(screen.getByLabelText("Carlos Mendes is muted")).toBeTruthy();
  });

  it("filters the list by search query", () => {
    render(<PeoplePanel participants={participants} />);

    fireEvent.change(screen.getByLabelText("Search for people"), {
      target: { value: "amina" },
    });

    expect(screen.getByText("Amina Yusuf")).toBeTruthy();
    expect(screen.queryByText("Carlos Mendes")).toBeNull();
  });

  it("collapses the participant group", () => {
    render(<PeoplePanel participants={participants} />);

    const group = screen.getByRole("button", { name: /Contributors/ });
    expect(group.getAttribute("aria-expanded")).toBe("true");

    fireEvent.click(group);
    expect(group.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText("Amina Yusuf")).toBeNull();
  });

  it("invites people through the handler", () => {
    const onAddPeople = vi.fn();
    render(<PeoplePanel participants={participants} onAddPeople={onAddPeople} />);

    fireEvent.click(screen.getByRole("button", { name: /Add people/ }));
    expect(onAddPeople).toHaveBeenCalledTimes(1);
  });

  it("offers host mute and remove actions, never for yourself", () => {
    const onMute = vi.fn();
    const onRemove = vi.fn();
    render(
      <PeoplePanel participants={participants} canManage onMute={onMute} onRemove={onRemove} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Mute Amina Yusuf" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove Carlos Mendes from the meet" }));
    expect(onMute).toHaveBeenCalledWith("amina");
    expect(onRemove).toHaveBeenCalledWith("carlos");

    expect(screen.queryByRole("button", { name: "Mute Hasan" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Remove Hasan from the meet" })).toBeNull();
  });

  it("keeps management actions hidden from non-hosts", () => {
    render(<PeoplePanel participants={participants} onMute={vi.fn()} onRemove={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Mute Amina Yusuf" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Remove Carlos Mendes from the meet" })).toBeNull();
  });
});

describe("ChatPanel", () => {
  it("shows an empty state before any messages", () => {
    render(<ChatPanel />);
    expect(screen.getByText("No messages yet")).toBeTruthy();
  });

  it("renders provided messages with author and time", () => {
    render(
      <ChatPanel messages={[{ id: "1", author: "Amina Yusuf", text: "Hello!", time: "10:12" }]} />,
    );

    expect(screen.getByText("Hello!")).toBeTruthy();
    expect(screen.getByText("Amina Yusuf")).toBeTruthy();
    expect(screen.getByText("10:12")).toBeTruthy();
  });

  it("disables the send button until a message is typed", () => {
    render(<ChatPanel />);
    const send = screen.getByRole("button", { name: "Send message" });
    expect(send.hasAttribute("disabled")).toBe(true);

    fireEvent.change(screen.getByLabelText("Send a message"), {
      target: { value: "Hi" },
    });
    expect(send.hasAttribute("disabled")).toBe(false);
  });

  it("submits the composer through the handler and clears it", () => {
    const onSend = vi.fn();
    render(<ChatPanel onSend={onSend} />);

    const input = screen.getByLabelText("Send a message");
    fireEvent.change(input, { target: { value: "Starting now" } });
    fireEvent.submit(input.closest("form") as HTMLFormElement);

    expect(onSend).toHaveBeenCalledWith("Starting now");
    expect((input as HTMLInputElement).value).toBe("");
  });

  it("exposes the host chat switch and the turned-off notice", () => {
    const onToggleAllowChat = vi.fn();
    const view = render(
      <ChatPanel canManage allowChat={true} onToggleAllowChat={onToggleAllowChat} />,
    );
    expect(screen.queryByText("Chat is turned off")).toBeNull();

    fireEvent.click(screen.getByRole("switch"));
    expect(onToggleAllowChat).toHaveBeenCalledWith(false);

    view.rerender(<ChatPanel canManage allowChat={false} onToggleAllowChat={onToggleAllowChat} />);
    expect(screen.getByText("Chat is turned off")).toBeTruthy();
    expect(screen.getByLabelText("Send a message").hasAttribute("disabled")).toBe(true);
  });

  it("hides the host switch from non-hosts", () => {
    render(<ChatPanel allowChat={true} />);
    expect(screen.queryByRole("switch")).toBeNull();
    expect(screen.queryByText("Chat is turned off")).toBeNull();
  });
});

describe("ReactionBar", () => {
  it("offers every reaction and hides itself", () => {
    const onReact = vi.fn();
    const onCollapse = vi.fn();
    render(<ReactionBar onReact={onReact} onCollapse={onCollapse} />);

    expect(screen.getByRole("toolbar", { name: "Reactions" })).toBeTruthy();
    expect(screen.getAllByRole("button").length).toBe(10);

    fireEvent.click(screen.getByRole("button", { name: "React with Thumbs up" }));
    fireEvent.click(screen.getByRole("button", { name: "Hide reactions" }));

    expect(onReact).toHaveBeenCalledWith("Thumbs up");
    expect(onCollapse).toHaveBeenCalledTimes(1);
  });
});

describe("UtilityCluster", () => {
  function renderCluster(overrides: Partial<React.ComponentProps<typeof UtilityCluster>> = {}) {
    return render(
      <TooltipProvider>
        <UtilityCluster
          onOpenChat={vi.fn()}
          onOpenPeople={vi.fn()}
          onToggleHostControls={vi.fn()}
          {...overrides}
        />
      </TooltipProvider>,
    );
  }

  it("exposes panel toggles with pressed state", () => {
    const onOpenChat = vi.fn();
    renderCluster({ onOpenChat, isChatOpen: true, isPeopleOpen: false });

    const chat = screen.getByRole("button", { name: "Open chat" });
    expect(chat.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "Show people" }).getAttribute("aria-pressed")).toBe(
      "false",
    );

    fireEvent.click(chat);
    expect(onOpenChat).toHaveBeenCalledTimes(1);
  });
});
