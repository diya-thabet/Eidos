import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Users } from "lucide-react";

export default function AdminUsersPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">User Management</h1>
      <Card>
        <CardContent className="p-0">
          <table className="w-full">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-muted-foreground">User</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-muted-foreground">Email</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-muted-foreground">Role</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-muted-foreground">Joined</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-muted-foreground">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr><td colSpan={5} className="px-4 py-12 text-center text-sm text-muted-foreground">Loading users...</td></tr>
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
