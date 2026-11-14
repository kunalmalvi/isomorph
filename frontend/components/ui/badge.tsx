import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium", {
  variants: {
    tone: {
      neutral: "bg-muted text-muted-foreground",
      blue: "border-primary/40 bg-primary/10 text-primary",
      violet: "border-accent/40 bg-accent/10 text-accent",
      cyan: "border-cyan/40 bg-cyan/10 text-cyan",
      success: "border-success/40 bg-success/10 text-success",
      warning: "border-warning/40 bg-warning/10 text-warning",
      danger: "border-danger/40 bg-danger/10 text-danger",
    },
  },
  defaultVariants: { tone: "neutral" },
});

export type Tone = NonNullable<VariantProps<typeof badgeVariants>["tone"]>;

export function Badge({ className, tone, ...props }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}

const STATUS_TONE: Record<string, Tone> = {
  done: "success", ok: "success", validated: "success", supported: "success", running: "blue", queued: "neutral", pending: "neutral",
  failed: "danger", blocked: "danger", rejected: "danger", refuted: "danger", cancelled: "warning", stale: "warning",
  untested: "neutral", inconclusive: "warning",
};

export function StatusBadge({ status }: { status: string }) {
  return <Badge tone={STATUS_TONE[status] ?? "neutral"}>{status}</Badge>;
}

const PROV_TONE: Record<string, Tone> = { source: "cyan", computation: "blue", user: "violet", ai_hypothesis: "warning" };

export function ProvenanceBadge({ provenance }: { provenance: string }) {
  return <Badge tone={PROV_TONE[provenance] ?? "neutral"} title="Where this claim comes from">{provenance}</Badge>;
}
