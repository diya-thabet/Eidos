"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { cn, scoreColor, severityColor } from "@/lib/utils";
import { HEALTH_CATEGORIES, SEVERITY_ORDER } from "@/lib/constants";
import {
  HeartPulse, Play, Settings2, Download, ChevronDown, ChevronUp,
  Sparkles, Shield, Activity, FileText, Type, Workflow, CheckCircle, Blocks,
} from "lucide-react";

const categoryIcons: Record<string, React.ElementType> = {
  clean_code: Sparkles, solid: Blocks, complexity: Activity,
  documentation: FileText, naming: Type, design: Workflow,
  security: Shield, best_practices: CheckCircle,
};

export default function HealthPage() {
  const [showConfig, setShowConfig] = useState(false);
  const [categories, setCategories] = useState<string[]>([]);
  const [severityFilter, setSeverityFilter] = useState("");
  const [useLlm, setUseLlm] = useState(false);
  const [thresholds, setThresholds] = useState({
    max_method_lines: 30,
    max_class_lines: 300,
    max_parameters: 5,
    max_fan_out: 10,
    max_fan_in: 15,
    max_children: 20,
    max_inheritance_depth: 4,
    max_god_class_methods: 15,
  });

  // Mock data — will be replaced with React Query
  const report = null as null | {
    overall_score: number;
    findings_count: number;
    findings: Array<{
      rule_id: string;
      rule_name: string;
      category: string;
      severity: string;
      symbol: string;
      file: string;
      line: number;
      message: string;
      suggestion: string;
    }>;
    summary: Record<string, number>;
    category_scores: Record<string, number>;
    llm_insights: Array<{ category: string; title: string; recommendation: string }>;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <HeartPulse className="h-6 w-6 text-primary" />
          <div>
            <h2 className="text-xl font-semibold">Code Health</h2>
            <p className="text-sm text-muted-foreground">40 rules across 8 categories</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setShowConfig(!showConfig)}>
            <Settings2 className="mr-2 h-4 w-4" />
            Configure
            {showConfig ? <ChevronUp className="ml-1 h-3 w-3" /> : <ChevronDown className="ml-1 h-3 w-3" />}
          </Button>
          <Button size="sm">
            <Play className="mr-2 h-4 w-4" /> Run Check
          </Button>
        </div>
      </div>

      {/* Configuration panel */}
      {showConfig && (
        <Card className="animate-slide-in">
          <CardHeader>
            <CardTitle className="text-base">Rule Configuration</CardTitle>
            <CardDescription>Customize which rules to run and their thresholds.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Categories */}
            <div>
              <label className="text-sm font-medium">Categories</label>
              <p className="text-xs text-muted-foreground mb-2">Leave empty to run all categories.</p>
              <div className="flex flex-wrap gap-2">
                {HEALTH_CATEGORIES.map((cat) => {
                  const active = categories.includes(cat.id);
                  const Icon = categoryIcons[cat.id] || CheckCircle;
                  return (
                    <button
                      key={cat.id}
                      onClick={() =>
                        setCategories(
                          active ? categories.filter((c) => c !== cat.id) : [...categories, cat.id],
                        )
                      }
                      className={cn(
                        "flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                        active
                          ? "border-primary bg-primary/10 text-primary"
                          : "border-border text-muted-foreground hover:border-primary/50",
                      )}
                    >
                      <Icon className="h-3 w-3" />
                      {cat.label}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Thresholds */}
            <div>
              <label className="text-sm font-medium">Thresholds</label>
              <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-4">
                {Object.entries(thresholds).map(([key, value]) => (
                  <div key={key} className="space-y-1">
                    <label className="text-xs text-muted-foreground">
                      {key.replace(/^max_/, "").replace(/_/g, " ")}
                    </label>
                    <Input
                      type="number"
                      className="h-8 text-xs"
                      value={value}
                      onChange={(e) =>
                        setThresholds((t) => ({ ...t, [key]: parseInt(e.target.value) || 0 }))
                      }
                    />
                  </div>
                ))}
              </div>
            </div>

            {/* LLM toggle */}
            <div className="flex items-center gap-3">
              <button
                onClick={() => setUseLlm(!useLlm)}
                className={cn(
                  "h-5 w-9 rounded-full transition-colors",
                  useLlm ? "bg-primary" : "bg-muted",
                )}
              >
                <span
                  className={cn(
                    "block h-4 w-4 rounded-full bg-white shadow transition-transform",
                    useLlm ? "translate-x-4" : "translate-x-0.5",
                  )}
                />
              </button>
              <div>
                <span className="text-sm font-medium">LLM-powered analysis</span>
                <p className="text-xs text-muted-foreground">
                  Get AI-generated refactoring advice and design pattern suggestions.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Score + Categories (empty state) */}
      {!report ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <HeartPulse className="h-16 w-16 text-muted-foreground/30" />
            <h3 className="mt-4 text-lg font-semibold">No health report yet</h3>
            <p className="mt-2 max-w-sm text-center text-sm text-muted-foreground">
              Run a health check to see your code&apos;s score across clean code, SOLID,
              complexity, naming, security, and more.
            </p>
            <Button className="mt-6" size="sm">
              <Play className="mr-2 h-4 w-4" /> Run Check
            </Button>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Score gauge */}
          <div className="grid gap-4 sm:grid-cols-3">
            <Card className="sm:col-span-1">
              <CardContent className="flex flex-col items-center justify-center py-8">
                <div className={cn("text-5xl font-bold", scoreColor(report.overall_score))}>
                  {report.overall_score}
                </div>
                <p className="mt-1 text-sm text-muted-foreground">/ 100</p>
                <p className="mt-2 text-xs font-medium text-muted-foreground">Overall Score</p>
              </CardContent>
            </Card>

            {/* Category scores */}
            <Card className="sm:col-span-2">
              <CardHeader><CardTitle className="text-base">Category Scores</CardTitle></CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {HEALTH_CATEGORIES.map((cat) => {
                    const score = report.category_scores[cat.id] ?? 100;
                    const Icon = categoryIcons[cat.id] || CheckCircle;
                    return (
                      <div key={cat.id} className="flex flex-col items-center gap-1 rounded-lg border p-3">
                        <Icon className="h-4 w-4 text-muted-foreground" />
                        <span className={cn("text-lg font-bold", scoreColor(score))}>{score}</span>
                        <span className="text-xs text-muted-foreground">{cat.label}</span>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Findings */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base">
                Findings <Badge variant="secondary" className="ml-2">{report.findings_count}</Badge>
              </CardTitle>
              <div className="flex gap-2">
                {SEVERITY_ORDER.map((sev) => (
                  <button
                    key={sev}
                    onClick={() => setSeverityFilter(severityFilter === sev ? "" : sev)}
                    className={cn(
                      "rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors",
                      severityFilter === sev ? severityColor(sev) : "bg-muted text-muted-foreground",
                    )}
                  >
                    {sev} ({report.summary[sev] ?? 0})
                  </button>
                ))}
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <table className="w-full">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase text-muted-foreground">Severity</th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase text-muted-foreground">Rule</th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase text-muted-foreground">Message</th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase text-muted-foreground">Location</th>
                  </tr>
                </thead>
                <tbody>
                  {report.findings
                    .filter((f) => !severityFilter || f.severity === severityFilter)
                    .map((f, i) => (
                      <tr key={i} className="border-b hover:bg-muted/30 transition-colors">
                        <td className="px-4 py-3">
                          <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", severityColor(f.severity))}>
                            {f.severity}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className="font-mono text-xs">{f.rule_id}</span>
                          <span className="ml-1 text-xs text-muted-foreground">{f.rule_name}</span>
                        </td>
                        <td className="px-4 py-3 text-sm">{f.message}</td>
                        <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                          {f.file}:{f.line}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
