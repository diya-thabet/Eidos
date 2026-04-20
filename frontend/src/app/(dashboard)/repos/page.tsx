import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Plus, FolderGit2 } from "lucide-react";

export default function ReposPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Repositories</h1>
          <p className="text-muted-foreground">Manage and analyze your code repositories.</p>
        </div>
        <Link href="/repos/new">
          <Button><Plus className="mr-2 h-4 w-4" /> Add Repository</Button>
        </Link>
      </div>

      {/* Empty state */}
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-16">
          <FolderGit2 className="h-16 w-16 text-muted-foreground/30" />
          <h3 className="mt-4 text-lg font-semibold">No repositories yet</h3>
          <p className="mt-2 max-w-sm text-center text-sm text-muted-foreground">
            Add your first repository to start analyzing code health, browsing symbols,
            and asking questions about your codebase.
          </p>
          <Link href="/repos/new">
            <Button className="mt-6"><Plus className="mr-2 h-4 w-4" /> Add Repository</Button>
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
