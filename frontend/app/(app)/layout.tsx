import { Suspense } from "react";
import { AppShell } from "@/components/shell/app-shell";
import { LoadingState } from "@/components/ui/states";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell>
      <Suspense fallback={<LoadingState />}>{children}</Suspense>
    </AppShell>
  );
}
