import { describe, expect, it } from "vitest";

import { cn } from "@/lib/utils";

describe("cn", () => {
  it("joins truthy class names", () => {
    expect(cn("p-2", true && "font-bold", "text-sm")).toBe("p-2 font-bold text-sm");
  });

  it("drops falsy class names", () => {
    expect(cn("p-2", false && "p-4", "text-sm")).toBe("p-2 text-sm");
  });

  it("keeps the last class when Tailwind utilities conflict", () => {
    expect(cn("p-2", "p-4")).toBe("p-4");
  });
});
