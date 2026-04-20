import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BarChart3 } from "lucide-react";

export default function AdminUsagePage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Usage Analytics</h1>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-base">Scans per Day</CardTitle></CardHeader>
          <CardContent className="flex items-center justify-center py-16">
            <BarChart3 className="h-12 w-12 text-muted-foreground/30" />
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">Tokens Used per Day</CardTitle></CardHeader>
          <CardContent className="flex items-center justify-center py-16">
            <BarChart3 className="h-12 w-12 text-muted-foreground/30" />
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">Top Users</CardTitle></CardHeader>
          <CardContent><p className="text-sm text-muted-foreground">No usage data yet.</p></CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">Usage by Plan</CardTitle></CardHeader>
          <CardContent><p className="text-sm text-muted-foreground">No usage data yet.</p></CardContent>
        </Card>
      </div>
    </div>
  );
}
