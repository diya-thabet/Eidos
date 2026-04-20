"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, FolderGit2, Server, Users, CreditCard, BarChart3,
  ChevronLeft, ChevronRight, HeartPulse, Settings,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useSidebarStore } from "@/stores/sidebar-store";

const icons: Record<string, React.ElementType> = {
  LayoutDashboard, FolderGit2, Server, Users, CreditCard, BarChart3, HeartPulse, Settings,
};

const mainNav = [
  { href: "/", label: "Dashboard", icon: "LayoutDashboard" },
  { href: "/repos", label: "Repositories", icon: "FolderGit2" },
];

const adminNav = [
  { href: "/admin", label: "System", icon: "Server" },
  { href: "/admin/users", label: "Users", icon: "Users" },
  { href: "/admin/plans", label: "Plans", icon: "CreditCard" },
  { href: "/admin/usage", label: "Usage", icon: "BarChart3" },
];

export function Sidebar() {
  const pathname = usePathname();
  const { collapsed, toggle } = useSidebarStore();

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-30 flex flex-col border-r bg-sidebar transition-all duration-300",
        collapsed ? "w-16" : "w-64",
      )}
    >
      {/* Logo */}
      <div className="flex h-16 items-center gap-3 border-b px-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold text-sm">
          E
        </div>
        {!collapsed && <span className="text-lg font-semibold">Eidos</span>}
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 overflow-y-auto p-3">
        <p className={cn("mb-2 text-xs font-medium uppercase text-muted-foreground", collapsed && "sr-only")}>
          Main
        </p>
        {mainNav.map((item) => {
          const Icon = icons[item.icon];
          const active = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-sidebar-accent text-foreground"
                  : "text-muted-foreground hover:bg-sidebar-accent hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}

        <div className="my-4 border-t" />
        <p className={cn("mb-2 text-xs font-medium uppercase text-muted-foreground", collapsed && "sr-only")}>
          Admin
        </p>
        {adminNav.map((item) => {
          const Icon = icons[item.icon];
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-sidebar-accent text-foreground"
                  : "text-muted-foreground hover:bg-sidebar-accent hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Collapse toggle */}
      <div className="border-t p-3">
        <button
          onClick={toggle}
          className="flex w-full items-center justify-center rounded-md p-2 text-muted-foreground hover:bg-sidebar-accent hover:text-foreground"
        >
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </button>
      </div>
    </aside>
  );
}
