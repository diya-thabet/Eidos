export const APP_NAME = "Eidos";
export const APP_DESCRIPTION = "Legacy Code Intelligence";

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const SEVERITY_ORDER = ["critical", "error", "warning", "info"] as const;

export const HEALTH_CATEGORIES = [
  { id: "clean_code", label: "Clean Code", icon: "Sparkles" },
  { id: "solid", label: "SOLID", icon: "Blocks" },
  { id: "complexity", label: "Complexity", icon: "Activity" },
  { id: "documentation", label: "Documentation", icon: "FileText" },
  { id: "naming", label: "Naming", icon: "Type" },
  { id: "design", label: "Design", icon: "Workflow" },
  { id: "security", label: "Security", icon: "Shield" },
  { id: "best_practices", label: "Best Practices", icon: "CheckCircle" },
] as const;

export const SYMBOL_KINDS = [
  "class", "interface", "struct", "enum", "method",
  "constructor", "property", "field", "delegate", "record", "namespace",
] as const;

export const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: "LayoutDashboard" },
  { href: "/repos", label: "Repositories", icon: "FolderGit2" },
] as const;

export const ADMIN_NAV_ITEMS = [
  { href: "/admin", label: "System", icon: "Server" },
  { href: "/admin/users", label: "Users", icon: "Users" },
  { href: "/admin/plans", label: "Plans", icon: "CreditCard" },
  { href: "/admin/usage", label: "Usage", icon: "BarChart3" },
] as const;

export const SNAPSHOT_NAV_ITEMS = [
  { segment: "", label: "Overview", icon: "BarChart3" },
  { segment: "symbols", label: "Symbols", icon: "Code" },
  { segment: "graph", label: "Graph", icon: "Workflow" },
  { segment: "health", label: "Health", icon: "HeartPulse" },
  { segment: "ask", label: "Q&A", icon: "MessageSquare" },
  { segment: "review", label: "Review", icon: "GitPullRequest" },
  { segment: "docs", label: "Docs", icon: "FileText" },
] as const;
