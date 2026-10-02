import { describe, expect, it } from "vitest";

import { badgeVariants } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";

describe("status variants", () => {
  it("button success uses the success token pair", () => {
    const classes = buttonVariants({ variant: "success" });
    expect(classes).toContain("bg-success");
    expect(classes).toContain("text-success-foreground");
  });

  it("badge status variants tint with their own tokens", () => {
    expect(badgeVariants({ variant: "success" })).toContain("text-success");
    expect(badgeVariants({ variant: "warning" })).toContain("text-warning");
    expect(badgeVariants({ variant: "info" })).toContain("text-info");
    expect(badgeVariants({ variant: "destructive" })).toContain("text-destructive");
  });

  it("no variant leaks raw palette colors", () => {
    const variants = [
      "default",
      "secondary",
      "outline",
      "ghost",
      "link",
      "destructive",
      "success",
      "warning",
      "info",
    ] as const;

    for (const variant of variants) {
      expect(badgeVariants({ variant })).not.toMatch(
        /bg-(blue|emerald|red|green|amber|indigo|gray|slate)-/,
      );
    }
  });
});
