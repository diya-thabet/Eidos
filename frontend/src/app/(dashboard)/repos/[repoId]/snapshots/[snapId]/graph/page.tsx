import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Workflow } from "lucide-react";

export default function GraphPage() {
  return (
    <Card className="min-h-[600px]">
      <CardHeader>
        <CardTitle className="text-lg">Code Graph</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col items-center justify-center py-24">
        <Workflow className="h-16 w-16 text-muted-foreground/30" />
        <h3 className="mt-4 text-lg font-medium">Graph Visualization</h3>
        <p className="mt-2 max-w-md text-center text-sm text-muted-foreground">
          Interactive call graph and dependency visualization powered by React Flow.
          Run a scan to populate the graph with symbols and their relationships.
        </p>
      </CardContent>
    </Card>
  );
}
