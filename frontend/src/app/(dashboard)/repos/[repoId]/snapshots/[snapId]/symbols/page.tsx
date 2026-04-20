"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Search, Filter } from "lucide-react";

export default function SymbolsPage() {
  const [search, setSearch] = useState("");
  const [kindFilter, setKindFilter] = useState("");

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search symbols by name or fq_name..."
            className="pl-9"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select
          className="h-10 rounded-md border bg-background px-3 text-sm"
          value={kindFilter}
          onChange={(e) => setKindFilter(e.target.value)}
        >
          <option value="">All kinds</option>
          <option value="class">Class</option>
          <option value="method">Method</option>
          <option value="interface">Interface</option>
          <option value="struct">Struct</option>
          <option value="enum">Enum</option>
          <option value="field">Field</option>
          <option value="property">Property</option>
          <option value="constructor">Constructor</option>
        </select>
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          <table className="w-full">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-muted-foreground">Name</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-muted-foreground">Kind</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-muted-foreground">File</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-muted-foreground">Lines</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td colSpan={4} className="px-4 py-12 text-center text-sm text-muted-foreground">
                  No symbols found. Run an analysis scan first.
                </td>
              </tr>
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
