// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

import { shareOrCopyLink } from "./share";

function stubNavigator(key: "share" | "clipboard", value: unknown) {
  Object.defineProperty(window.navigator, key, { value, configurable: true });
}

afterEach(() => {
  stubNavigator("share", undefined);
  stubNavigator("clipboard", undefined);
});

describe("shareOrCopyLink", () => {
  it("uses the native share sheet when available", async () => {
    const share = vi.fn().mockResolvedValue(undefined);
    stubNavigator("share", share);

    const outcome = await shareOrCopyLink("https://x.test/room/abc-def", "Join my meet — Procto");

    expect(outcome).toBe("shared");
    expect(share).toHaveBeenCalledWith({
      title: "Join my meet — Procto",
      url: "https://x.test/room/abc-def",
    });
  });

  it("reports a dismissed share sheet as cancelled", async () => {
    stubNavigator("share", vi.fn().mockRejectedValue(new DOMException("dismissed", "AbortError")));

    expect(await shareOrCopyLink("https://x.test/room/abc-def", "t")).toBe("cancelled");
  });

  it("falls back to the clipboard when sharing fails", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    stubNavigator("share", vi.fn().mockRejectedValue(new Error("unsupported on this device")));
    stubNavigator("clipboard", { writeText });

    expect(await shareOrCopyLink("https://x.test/room/abc-def", "t")).toBe("copied");
    expect(writeText).toHaveBeenCalledWith("https://x.test/room/abc-def");
  });

  it("copies when no share sheet exists", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    stubNavigator("clipboard", { writeText });

    expect(await shareOrCopyLink("https://x.test/room/abc-def", "t")).toBe("copied");
    expect(writeText).toHaveBeenCalledTimes(1);
  });

  it("fails when neither sharing nor the clipboard is available", async () => {
    expect(await shareOrCopyLink("https://x.test/room/abc-def", "t")).toBe("failed");
  });

  it("fails when the clipboard rejects (permissions)", async () => {
    stubNavigator("clipboard", { writeText: vi.fn().mockRejectedValue(new Error("denied")) });

    expect(await shareOrCopyLink("https://x.test/room/abc-def", "t")).toBe("failed");
  });
});
