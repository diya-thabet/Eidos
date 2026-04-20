import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { HeartPulse, MessageSquare, FileText, GitPullRequest, Code, Shield, Sparkles, ArrowRight } from "lucide-react";

const features = [
  { icon: HeartPulse, title: "Code Health", description: "40 rules across 8 categories: SOLID, clean code, complexity, security, naming, and more." },
  { icon: MessageSquare, title: "Q&A Engine", description: "Ask questions about your codebase and get evidence-backed answers with file and line citations." },
  { icon: GitPullRequest, title: "PR Reviews", description: "Automated behavior-focused reviews that catch logic risks, not style nitpicks." },
  { icon: FileText, title: "Auto Documentation", description: "Generate accurate documentation with citations linking back to actual source code." },
  { icon: Code, title: "9 Languages", description: "C#, Java, Python, TypeScript/TSX, Go, Rust, C, C++ — all with full AST parsing." },
  { icon: Shield, title: "Security Analysis", description: "Detect hardcoded secrets, SQL injection risks, and insecure public fields." },
];

export default function LandingPage() {
  return (
    <div className="flex min-h-screen flex-col">
      {/* Navbar */}
      <nav className="border-b">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary font-bold text-primary-foreground text-sm">E</div>
            <span className="text-xl font-bold">Eidos</span>
          </div>
          <div className="flex items-center gap-4">
            <Link href="/login" className="text-sm text-muted-foreground hover:text-foreground">Sign in</Link>
            <Link href="/login"><Button size="sm">Get Started</Button></Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="mx-auto max-w-4xl px-6 py-24 text-center">
        <div className="inline-flex items-center gap-2 rounded-full border bg-muted px-4 py-1.5 text-sm">
          <Sparkles className="h-4 w-4 text-primary" />
          <span>40 code health rules — powered by AI</span>
        </div>
        <h1 className="mt-6 text-5xl font-bold tracking-tight sm:text-6xl">
          Intelligence for
          <span className="text-primary"> legacy code</span>
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground">
          Eidos explains your codebase, generates documentation, reviews PRs for behavior risks,
          and measures code health — all with evidence and confidence scores.
        </p>
        <div className="mt-8 flex justify-center gap-4">
          <Link href="/login"><Button size="lg">Start Free <ArrowRight className="ml-2 h-4 w-4" /></Button></Link>
          <Link href="/pricing"><Button variant="outline" size="lg">View Pricing</Button></Link>
        </div>
      </section>

      {/* Features */}
      <section className="border-t bg-muted/30 py-24">
        <div className="mx-auto max-w-6xl px-6">
          <h2 className="text-center text-3xl font-bold">Everything you need to understand legacy code</h2>
          <p className="mx-auto mt-4 max-w-2xl text-center text-muted-foreground">
            From static analysis to AI-powered explanations, Eidos is your complete code intelligence platform.
          </p>
          <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {features.map((f) => (
              <Card key={f.title} className="transition-shadow hover:shadow-md">
                <CardContent className="pt-6">
                  <f.icon className="h-10 w-10 text-primary" />
                  <h3 className="mt-4 text-lg font-semibold">{f.title}</h3>
                  <p className="mt-2 text-sm text-muted-foreground">{f.description}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t py-8">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6">
          <span className="text-sm text-muted-foreground">&copy; 2025 Eidos. All rights reserved.</span>
          <div className="flex gap-4 text-sm text-muted-foreground">
            <Link href="#" className="hover:text-foreground">Privacy</Link>
            <Link href="#" className="hover:text-foreground">Terms</Link>
            <Link href="https://github.com/diya-thabet/Eidos" className="hover:text-foreground">GitHub</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
