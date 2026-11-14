import {
  Archive, BookOpen, Dna, FlaskConical, FolderSearch, LayoutDashboard, Orbit, PlusCircle, Scale, Settings, Shapes,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  description: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Overview", description: "Platform totals and recent work", icon: LayoutDashboard },
  { href: "/new", label: "New Discovery", description: "Describe a problem and start a run", icon: PlusCircle },
  { href: "/investigations", label: "My Investigations", description: "All discovery runs", icon: FolderSearch },
  { href: "/dna", label: "Structural DNA", description: "Graph, metrics and fingerprint", icon: Dna },
  { href: "/universe", label: "Discovery Universe", description: "Cross domain matches", icon: Orbit },
  { href: "/transformation", label: "Transformation Studio", description: "Concepts derived from mappings", icon: Shapes },
  { href: "/hypotheses", label: "Hypothesis Arena", description: "Compare and curate hypotheses", icon: Scale },
  { href: "/validation", label: "Validation Lab", description: "Seeded simulation evidence", icon: FlaskConical },
  { href: "/archive", label: "Discovery Archive", description: "Archived projects and reports", icon: Archive },
  { href: "/library", label: "Knowledge Library", description: "Domains, systems and mechanisms", icon: BookOpen },
  { href: "/settings", label: "Settings", description: "Providers, weights and account", icon: Settings },
];
