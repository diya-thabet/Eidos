"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Send, Bot, User, Sparkles, ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";

interface Message {
  role: "user" | "assistant";
  content: string;
  evidence?: Array<{ file: string; symbol: string; lines: string }>;
  confidence?: string;
}

const suggestions = [
  "How does the authentication system work?",
  "What design patterns are used?",
  "Explain the main entry points",
  "What are the key dependencies?",
];

export default function AskPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const question = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setLoading(true);

    // TODO: Replace with api.reasoning.ask()
    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "This is a placeholder response. Connect the backend API to get real answers with evidence and confidence scores.",
          confidence: "medium",
          evidence: [
            { file: "example.cs", symbol: "ExampleClass.Run", lines: "10-25" },
          ],
        },
      ]);
      setLoading(false);
    }, 1500);
  };

  return (
    <div className="flex h-[calc(100vh-16rem)] flex-col">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 pb-4">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center">
            <Bot className="h-16 w-16 text-muted-foreground/30" />
            <h3 className="mt-4 text-lg font-semibold">Ask about your codebase</h3>
            <p className="mt-2 max-w-md text-center text-sm text-muted-foreground">
              Ask questions about architecture, patterns, dependencies, or any aspect of the code.
              Answers include evidence with file paths and line numbers.
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-2">
              {suggestions.map((q) => (
                <button
                  key={q}
                  onClick={() => { setInput(q); }}
                  className="rounded-full border px-3 py-1.5 text-xs text-muted-foreground hover:border-primary hover:text-primary transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg, i) => (
            <div key={i} className={cn("flex gap-3", msg.role === "user" ? "justify-end" : "justify-start")}>
              <div className={cn("flex gap-3 max-w-[80%]", msg.role === "user" && "flex-row-reverse")}>
                <div className={cn(
                  "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
                  msg.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted",
                )}>
                  {msg.role === "user" ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                </div>
                <div className={cn(
                  "rounded-2xl px-4 py-3 text-sm",
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted",
                )}>
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                  {msg.confidence && (
                    <div className="mt-2 flex items-center gap-2">
                      <Badge variant="outline" className="text-xs">Confidence: {msg.confidence}</Badge>
                    </div>
                  )}
                  {msg.evidence && msg.evidence.length > 0 && (
                    <div className="mt-3 space-y-1 border-t pt-2">
                      <p className="text-xs font-medium">Evidence:</p>
                      {msg.evidence.map((e, j) => (
                        <div key={j} className="flex items-center gap-1 text-xs font-mono opacity-80">
                          <ExternalLink className="h-3 w-3" />
                          {e.file}:{e.lines} — {e.symbol}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
        {loading && (
          <div className="flex gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted">
              <Bot className="h-4 w-4" />
            </div>
            <div className="rounded-2xl bg-muted px-4 py-3">
              <div className="flex gap-1">
                <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground/50" style={{ animationDelay: "0ms" }} />
                <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground/50" style={{ animationDelay: "150ms" }} />
                <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground/50" style={{ animationDelay: "300ms" }} />
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t pt-4">
        <form
          onSubmit={(e) => { e.preventDefault(); handleSend(); }}
          className="flex gap-2"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your codebase..."
            className="flex-1 rounded-lg border bg-background px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            disabled={loading}
          />
          <Button type="submit" size="icon" disabled={!input.trim() || loading} className="h-11 w-11">
            <Send className="h-4 w-4" />
          </Button>
        </form>
      </div>
    </div>
  );
}
