import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { FileText, Plus } from "lucide-react";

export default function DocsPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">Generated Documentation</h2>
          <p className="text-sm text-muted-foreground">Auto-generated docs with citations to actual code.</p>
        </div>
        <Button size="sm"><Plus className="mr-2 h-4 w-4" /> Generate Docs</Button>
      </div>

      <Card>
        <CardContent className="flex flex-col items-center justify-center py-16">
          <FileText className="h-16 w-16 text-muted-foreground/30" />
          <h3 className="mt-4 text-lg font-semibold">No documents yet</h3>
          <p className="mt-2 max-w-sm text-center text-sm text-muted-foreground">
            Generate documentation for your codebase. Each doc includes evidence
            linking back to the source code.
          </p>
          <Button className="mt-6" size="sm"><Plus className="mr-2 h-4 w-4" /> Generate Docs</Button>
        </CardContent>
      </Card>
    </div>
  );
}
