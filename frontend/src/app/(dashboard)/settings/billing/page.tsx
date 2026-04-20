import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CreditCard } from "lucide-react";

export default function BillingPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <h1 className="text-2xl font-bold">Billing</h1>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><CreditCard className="h-5 w-5" /> Current Plan</CardTitle>
          <CardDescription>Manage your subscription and payment method.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-lg border bg-muted/50 p-4">
            <div className="text-lg font-semibold">Free Plan</div>
            <p className="text-sm text-muted-foreground">3 repos, 10 scans/month, 50 questions/month</p>
          </div>
          <Button size="sm">Upgrade Plan</Button>
        </CardContent>
      </Card>
    </div>
  );
}
