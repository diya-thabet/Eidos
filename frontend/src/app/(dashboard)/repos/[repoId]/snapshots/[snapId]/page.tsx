import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Code, Workflow, Box, Zap } from "lucide-react";

const stats = [
  { label: "Symbols", value: "--", icon: Code },
  { label: "Edges", value: "--", icon: Workflow },
  { label: "Modules", value: "--", icon: Box },
  { label: "Entry Points", value: "--", icon: Zap },
];

export default function SnapshotOverviewPage() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((s) => (
          <Card key={s.label}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">{s.label}</CardTitle>
              <s.icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent><div className="text-2xl font-bold">{s.value}</div></CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-lg">Symbols by Kind</CardTitle></CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">Run a scan to see symbol distribution.</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-lg">Hotspots</CardTitle></CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">High complexity areas will appear here.</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
