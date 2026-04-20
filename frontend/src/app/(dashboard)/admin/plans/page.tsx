import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Plus } from "lucide-react";

export default function AdminPlansPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Plan Management</h1>
        <Button size="sm"><Plus className="mr-2 h-4 w-4" /> Create Plan</Button>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {["Free", "Pro", "Team", "Enterprise"].map((plan) => (
          <Card key={plan}>
            <CardHeader><CardTitle className="text-lg">{plan}</CardTitle></CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              <p>Configure limits, features, and pricing for the {plan} tier.</p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
