import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FolderGit2, HeartPulse, MessageSquare, GitPullRequest } from "lucide-react";

const stats = [
  { label: "Repositories", value: "--", icon: FolderGit2, color: "text-primary" },
  { label: "Health Checks", value: "--", icon: HeartPulse, color: "text-health-good" },
  { label: "Questions Asked", value: "--", icon: MessageSquare, color: "text-health-info" },
  { label: "PR Reviews", value: "--", icon: GitPullRequest, color: "text-health-warning" },
];

export default function DashboardPage() {
  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">Welcome to Eidos. Analyze, understand, and improve your codebase.</p>
      </div>

      {/* Stats grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <Card key={stat.label}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">{stat.label}</CardTitle>
              <stat.icon className={`h-4 w-4 ${stat.color}`} />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stat.value}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Recent activity */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Recent Activity</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <FolderGit2 className="h-12 w-12 text-muted-foreground/50" />
            <h3 className="mt-4 text-lg font-medium">No activity yet</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Add a repository to get started with code analysis.
            </p>
            <a
              href="/repos/new"
              className="mt-4 inline-flex items-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            >
              Add Repository
            </a>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
