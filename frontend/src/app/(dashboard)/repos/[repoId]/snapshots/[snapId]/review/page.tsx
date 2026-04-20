"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn, severityColor } from "@/lib/utils";
import { GitPullRequest, Play, ClipboardPaste } from "lucide-react";

export default function ReviewPage() {
  const [diff, setDiff] = useState("");
  const [loading, setLoading] = useState(false);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <GitPullRequest className="h-5 w-5" />
            PR Review
          </CardTitle>
          <CardDescription>
            Paste a git diff to get behavior-focused review findings.
            Eidos checks for logic risks, contract violations, and side effects — not style.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Diff</label>
            <textarea
              value={diff}
              onChange={(e) => setDiff(e.target.value)}
              placeholder="Paste your git diff here... (git diff main..feature)"
              className="min-h-[200px] w-full rounded-md border bg-background p-3 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <div className="flex gap-2">
            <Button
              onClick={async () => {
                const text = await navigator.clipboard.readText();
                setDiff(text);
              }}
              variant="outline"
              size="sm"
            >
              <ClipboardPaste className="mr-2 h-4 w-4" /> Paste from clipboard
            </Button>
            <Button size="sm" disabled={!diff.trim() || loading}>
              <Play className="mr-2 h-4 w-4" /> {loading ? "Reviewing..." : "Run Review"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Empty state for results */}
      <Card>
        <CardHeader><CardTitle className="text-base">Review History</CardTitle></CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No reviews yet. Submit a diff to get started.</p>
        </CardContent>
      </Card>
    </div>
  );
}
