import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Server, Users, FolderGit2, HeartPulse, Shield, Cpu } from "lucide-react";

const sysStats = [
  { label: "Users", value: "--", icon: Users },
  { label: "Repositories", value: "--", icon: FolderGit2 },
  { label: "Health Rules", value: "40", icon: HeartPulse },
  { label: "Parsers", value: "9", icon: Cpu },
];

export default function AdminPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Shield className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold">System Administration</h1>
          <p className="text-sm text-muted-foreground">Monitor and manage the Eidos platform.</p>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {sysStats.map((s) => (
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
          <CardHeader><CardTitle className="text-lg">System Info</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between"><span className="text-muted-foreground">Edition</span><Badge>internal</Badge></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Version</span><span className="font-mono">0.2.0</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Auth</span><Badge variant="success">Enabled</Badge></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Languages</span><span>C#, Java, Python, TS/TSX, Go, Rust, C, C++</span></div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-lg">Recent Actions</CardTitle></CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">Audit log will appear here when events are recorded.</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
