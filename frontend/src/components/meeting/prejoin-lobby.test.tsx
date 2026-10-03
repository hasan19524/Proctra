// @vitest-environment jsdom
import * as React from "react";

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { PreJoinLobby, type JoinOptions } from "@/components/meeting/prejoin-lobby";

afterEach(cleanup);

function renderLobby(overrides: Partial<React.ComponentProps<typeof PreJoinLobby>> = {}) {
  const onJoin = vi.fn();
  render(
    <PreJoinLobby code="ktq-vxm-pnz" defaultName="Hasan Ali" onJoin={onJoin} {...overrides} />,
  );
  return { onJoin };
}

describe("PreJoinLobby", () => {
  it("shows the invite code and meeting title", () => {
    renderLobby({ title: "Sprint review" });

    expect(screen.getByText("Sprint review")).toBeTruthy();
    expect(screen.getByRole("button", { name: /copy invite code ktq-vxm-pnz/i })).toBeTruthy();
  });

  it("falls back to a clear message when the camera is unavailable", async () => {
    renderLobby();

    expect(await screen.findByText(/camera unavailable/i)).toBeTruthy();
    expect(screen.getByLabelText("Camera preview")).toBeTruthy();
  });

  it("toggles mic and camera with accessible pressed state", async () => {
    renderLobby();

    const mic = screen.getByRole("button", { name: /turn off microphone/i });
    expect(mic.getAttribute("aria-pressed")).toBe("false");

    fireEvent.click(mic);
    const micOff = screen.getByRole("button", { name: /turn on microphone/i });
    expect(micOff.getAttribute("aria-pressed")).toBe("true");

    expect(await screen.findByText("Camera unavailable — check browser permissions")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /turn off camera/i }));
    expect(screen.getByText("Camera is off")).toBeTruthy();
  });

  it("disables Join now while the name is empty and joins with trimmed options", () => {
    const { onJoin } = renderLobby();

    const join = screen.getByRole("button", { name: /join now/i });
    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "   " } });
    expect((join as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "  Ẑed  " } });
    expect((join as HTMLButtonElement).disabled).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: /turn off microphone/i }));
    fireEvent.click(screen.getByRole("button", { name: /turn off camera/i }));
    fireEvent.click(screen.getByRole("button", { name: /join now/i }));

    expect(onJoin).toHaveBeenCalledTimes(1);
    const options: JoinOptions = onJoin.mock.calls[0]?.[0];
    expect(options).toEqual({ displayName: "Ẑed", micOn: false, cameraOn: false });
  });

  it("uses the display name for the initials fallback", async () => {
    renderLobby({ defaultName: "Amina Yusuf" });

    expect(await screen.findByText("AY")).toBeTruthy();
  });
});
