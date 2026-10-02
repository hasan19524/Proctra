"use client";

import { ChevronDownIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "cn";

const REACTIONS = [
  { emoji: "❤️", label: "Heart" },
  { emoji: "👍", label: "Thumbs up" },
  { emoji: "🎉", label: "Party" },
  { emoji: "👏", label: "Clap" },
  { emoji: "😄", label: "Laugh" },
  { emoji: "😮", label: "Wow" },
  { emoji: "😢", label: "Sad" },
  { emoji: "😡", label: "Angry" },
  { emoji: "👎", label: "Thumbs down" },
] as const;

function ReactionBar({
  className,
  onReact,
  onCollapse,
}: {
  className?: string;
  onReact?: (label: string) => void;
  onCollapse?: () => void;
}) {
  return (
    <div
      role="toolbar"
      aria-label="Reactions"
      className={cn(
        "bg-card/95 flex w-fit max-w-full items-center gap-1 overflow-x-auto rounded-full border px-3 py-2 shadow-lg backdrop-blur",
        className,
      )}
    >
      {REACTIONS.map(({ emoji, label }) => (
        <button
          key={label}
          type="button"
          aria-label={`React with ${label}`}
          onClick={() => onReact?.(label)}
          className="hover:bg-muted focus-visible:ring-ring/50 flex size-9 shrink-0 items-center justify-center rounded-full text-lg transition-transform duration-150 hover:scale-110 focus-visible:ring-3 focus-visible:outline-none"
        >
          <span aria-hidden="true">{emoji}</span>
        </button>
      ))}
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label="Hide reactions"
        onClick={onCollapse}
        className="ml-1 rounded-full"
      >
        <ChevronDownIcon />
      </Button>
    </div>
  );
}

export { ReactionBar, REACTIONS };
