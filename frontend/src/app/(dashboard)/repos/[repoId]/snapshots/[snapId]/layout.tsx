"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, Code, Workflow, HeartPulse, MessageSquare, GitPullRequest, FileText } from "lucide-react";
import { cn } from "@/lib/utils";

const icons: Record<string, React.ElementType> = {
  BarChart3, Code, Workflow, HeartPulse, MessageSquare, GitPullRequest, FileText,
};

const tabs = [
  { segment: "", label: "Overview", icon: "BarChart3" },
  { segment: "symbols", label: "Symbols", icon: "Code" },
  { segment: "graph", label: "Graph", icon: "Workflow" },
  { segment: "health", label: "Health", icon: "HeartPulse" },
  { segment: "ask", label: "Q&A", icon: "MessageSquare" },
  { segment: "review", label: "Review", icon: "GitPullRequest" },
  { segment: "docs", label: "Docs", icon: "FileText" },
];

export default function SnapshotLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: { repoId: string; snapId: string };
}) {
  const pathname = usePathname();
  const base = `/repos/${params.repoId}/snapshots/${params.snapId}`;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Snapshot</h1>
        <p className="text-sm text-muted-foreground font-mono">{params.snapId}</p>
      </div>

      {/* Tab navigation */}
      <nav className="flex gap-1 overflow-x-auto rounded-lg border bg-muted/50 p-1">
        {tabs.map((tab) => {
          const href = tab.segment ? `${base}/${tab.segment}` : base;
          const active = tab.segment
            ? pathname.endsWith(`/${tab.segment}`)
            : pathname === base;
          const Icon = icons[tab.icon];
          return (
            <Link
              key={tab.segment}
              href={href}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors whitespace-nowrap",
                active
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              {tab.label}
            </Link>
          );
        })}
      </nav>

      {children}
    </div>
  );
}
