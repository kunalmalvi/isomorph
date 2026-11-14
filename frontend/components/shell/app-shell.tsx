"use client";
import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Command, Menu, Hexagon, X } from "lucide-react";
import { NAV_ITEMS } from "./nav";
import { CommandPalette } from "./command-palette";
import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/ui/states";
import { tokenStore } from "@/services/api";
import { cn } from "@/lib/utils";
import { isActive } from "@/lib/commands";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = React.useState(false);
  const [menuOpen, setMenuOpen] = React.useState(false);
  const [paletteOpen, setPaletteOpen] = React.useState(false);

  React.useEffect(() => {
    if (!tokenStore.get()) router.replace("/login");
    else setReady(true);
  }, [router]);

  React.useEffect(() => setMenuOpen(false), [pathname]);

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  if (!ready) {
    return (
      <div className="p-8">
        <LoadingState />
      </div>
    );
  }

  const nav = (
    <nav aria-label="Primary" className="flex flex-col gap-0.5 p-3">
      {NAV_ITEMS.map((item) => {
        const active = isActive(pathname, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm",
              active ? "bg-primary/15 text-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            <item.icon className={cn("h-4 w-4", active && "text-primary")} />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[250px_1fr]">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-card focus:p-2">
        Skip to content
      </a>
      <aside className="hidden border-r bg-card/50 lg:block">
        <div className="flex h-14 items-center gap-2 border-b px-5 font-display font-semibold">
          <Hexagon className="h-5 w-5 text-primary" /> ISOMORPH
        </div>
        {nav}
      </aside>

      {menuOpen && (
        <div className="fixed inset-0 z-40 bg-black/60 lg:hidden" onMouseDown={(e) => e.target === e.currentTarget && setMenuOpen(false)}>
          <aside className="h-full w-64 border-r bg-card">
            <div className="flex h-14 items-center justify-between border-b px-4 font-display font-semibold">
              <span>ISOMORPH</span>
              <Button variant="ghost" size="icon" aria-label="Close menu" onClick={() => setMenuOpen(false)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
            {nav}
          </aside>
        </div>
      )}

      <div className="min-w-0">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b bg-background/80 px-4 backdrop-blur">
          <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open menu" onClick={() => setMenuOpen(true)}>
            <Menu className="h-4 w-4" />
          </Button>
          <div className="flex-1" />
          <Button variant="secondary" size="sm" onClick={() => setPaletteOpen(true)} aria-label="Open command palette">
            <Command className="h-3.5 w-3.5" /> Search
            <kbd className="ml-2 hidden rounded border px-1 font-mono text-[10px] text-muted-foreground sm:inline">Ctrl K</kbd>
          </Button>
        </header>
        <main id="main" className="mx-auto max-w-7xl p-4 sm:p-6">
          {children}
        </main>
      </div>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
