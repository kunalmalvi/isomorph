import { cn } from "@/lib/utils";

export function JsonView({ value, className }: { value: unknown; className?: string }) {
  return (
    <pre tabIndex={0} className={cn("max-h-96 overflow-auto rounded-md border bg-background p-3 font-mono text-xs leading-relaxed", className)}>
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}
