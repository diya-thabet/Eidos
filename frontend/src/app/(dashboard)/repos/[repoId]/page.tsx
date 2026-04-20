import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Play, Clock, FileCode, GitBranch } from "lucide-react";

export default function RepoDetailPage({ params }: { params: { repoId: string } }) {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Repository</h1>
          <p className="text-sm text-muted-foreground font-mono">{params.repoId}</p>
        </div>
        <Button><Play className="mr-2 h-4 w-4" /> Run Scan</Button>
      </div>

      {/* Repo info */}
      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Branch</CardTitle>
            <GitBranch className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent><div className="text-lg font-semibold">main</div></CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Last Scan</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent><div className="text-lg font-semibold">--</div></CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Files</CardTitle>
            <FileCode className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent><div className="text-lg font-semibold">--</div></CardContent>
        </Card>
      </div>

      {/* Snapshots timeline */}
      <Card>
        <CardHeader><CardTitle className="text-lg">Scan History</CardTitle></CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No scans yet. Click "Run Scan" to analyze this repository.</p>
        </CardContent>
      </Card>
    </div>
  );
}
