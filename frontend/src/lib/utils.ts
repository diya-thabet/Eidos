import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(date: string | Date): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(date));
}

export function formatRelative(date: string | Date): string {
  const now = Date.now();
  const then = new Date(date).getTime();
  const diff = now - then;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return formatDate(date);
}

export function truncate(str: string, max: number): string {
  return str.length > max ? str.slice(0, max) + "..." : str;
}

export function scoreColor(score: number): string {
  if (score >= 90) return "text-health-good";
  if (score >= 70) return "text-health-warning";
  if (score >= 50) return "text-health-error";
  return "text-health-critical";
}

export function severityColor(severity: string): string {
  switch (severity) {
    case "critical": return "bg-health-critical text-white";
    case "error": return "bg-health-error text-white";
    case "warning": return "bg-health-warning text-white";
    default: return "bg-health-info text-white";
  }
}
