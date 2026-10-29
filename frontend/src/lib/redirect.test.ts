// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

import { readNextPath, sanitizeNextPath } from "./redirect";

describe("sanitizeNextPath", () => {
  it("accepts same-origin paths", () => {
    expect(sanitizeNextPath("/room/abc-def-ghi")).toBe("/room/abc-def-ghi");
    expect(sanitizeNextPath("/")).toBe("/");
    expect(sanitizeNextPath("/login")).toBe("/login");
  });

  it("rejects external and protocol-relative URLs (open-redirect guard)", () => {
    expect(sanitizeNextPath("https://evil.test")).toBeNull();
    expect(sanitizeNextPath("//evil.test")).toBeNull();
    expect(sanitizeNextPath("javascript:alert(1)")).toBeNull();
    expect(sanitizeNextPath("/\\evil.test")).toBeNull();
    expect(sanitizeNextPath("room/abc")).toBeNull();
    expect(sanitizeNextPath(null)).toBeNull();
    expect(sanitizeNextPath("")).toBeNull();
  });
});

describe("readNextPath", () => {
  it("reads and sanitises ?next= from the current URL", () => {
    window.history.pushState({}, "", "/login?next=%2Froom%2Fabc-def");
    expect(readNextPath()).toBe("/room/abc-def");
  });

  it("ignores external destinations", () => {
    window.history.pushState({}, "", "/login?next=https%3A%2F%2Fevil.test");
    expect(readNextPath()).toBeNull();
  });

  it("returns null without ?next=", () => {
    window.history.pushState({}, "", "/login");
    expect(readNextPath()).toBeNull();
  });
});
