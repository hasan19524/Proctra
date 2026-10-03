// @vitest-environment jsdom
import * as React from "react";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, act } from "@testing-library/react";

import { ApiError } from "@/lib/api";
import { TooltipProvider } from "@/components/ui/tooltip";

const { getMeetingMock, pushMock, codeParam } = vi.hoisted(() => ({
  getMeetingMock: vi.fn(),
  pushMock: vi.fn(),
  codeParam: { value: "ktq-vxm-pnz" },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn() }),
  useParams: () => ({ code: codeParam.value }),
}));

vi.mock("next/link", () => ({
  default: function LinkMock({
    href,
    children,
    ...rest
  }: React.ComponentProps<"a"> & { href: string }) {
    return (
      <a href={href} {...rest}>
        {children}
      </a>
    );
  },
}));

vi.mock("@/components/auth/session-context", () => ({
  RequireSession: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useSession: () => ({
    status: "authenticated",
    user: { id: "u-1", display_name: "Hasan Ali", email: "hasan@example.com" },
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  }),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, meetingsApi: { ...actual.meetingsApi, get: getMeetingMock } };
});

import RoomPage from "./page";

const meeting = {
  id: "m-1",
  code: "ktq-vxm-pnz",
  title: "Sprint review",
  host_id: "u-1",
  status: "waiting",
  is_locked: false,
  created_at: "2026-10-03T00:00:00Z",
  started_at: null,
  ended_at: null,
};

async function renderRoom(code = "ktq-vxm-pnz") {
  codeParam.value = code;
  const view = render(
    <TooltipProvider>
      <RoomPage />
    </TooltipProvider>,
  );
  await act(async () => {});
  return view;
}

beforeEach(() => {
  getMeetingMock.mockReset();
  pushMock.mockReset();
});

afterEach(cleanup);

describe("RoomPage", () => {
  it("shows a loading state until the meeting resolves", async () => {
    getMeetingMock.mockReturnValue(new Promise(() => {}));

    await renderRoom("nope");

    expect(screen.getByRole("status", { name: "Loading meeting" })).toBeTruthy();
  });

  it("shows a not-found screen for an unknown code", async () => {
    getMeetingMock.mockRejectedValue(new ApiError(404, "Meeting not found"));

    await renderRoom("nope");

    expect(await screen.findByText("Meeting not found")).toBeTruthy();
    expect(screen.getByText(/no meet matches the code nope/i)).toBeTruthy();
  });

  it("shows an ended screen when the meeting already ended", async () => {
    getMeetingMock.mockResolvedValue({ ...meeting, status: "ended" });

    await renderRoom();

    expect(await screen.findByText("This meet has ended")).toBeTruthy();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("opens the pre-join lobby, then the call with the chosen options", async () => {
    getMeetingMock.mockResolvedValue(meeting);

    await renderRoom();

    expect(await screen.findByText("Sprint review")).toBeTruthy();
    expect(screen.getByText(/check your camera and microphone/i)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /turn off camera/i }));
    fireEvent.click(screen.getByRole("button", { name: /join now/i }));

    expect(await screen.findByRole("button", { name: /leave/i })).toBeTruthy();
    expect(screen.getAllByText("ktq-vxm-pnz").length).toBeGreaterThan(0);
    expect(screen.queryByText(/check your camera and microphone/i)).toBeNull();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("leaves the call back to the home page", async () => {
    getMeetingMock.mockResolvedValue(meeting);

    await renderRoom();
    fireEvent.click(await screen.findByRole("button", { name: /join now/i }));
    fireEvent.click(await screen.findByRole("button", { name: /leave/i }));

    expect(pushMock).toHaveBeenCalledWith("/");
  });
});
