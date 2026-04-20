import { useState, useCallback } from "react";
import { api } from "@/lib/api-client";
import type { AskResponse } from "@/lib/api-client";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  evidence?: AskResponse["evidence"];
  confidence?: string;
}

export function useChat(repoId: string, snapId: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);

  const send = useCallback(
    async (question: string) => {
      setMessages((prev) => [...prev, { role: "user", content: question }]);
      setLoading(true);
      try {
        const res = await api.reasoning.ask(repoId, snapId, { question });
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: res.answer,
            evidence: res.evidence,
            confidence: res.confidence,
          },
        ]);
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: "Sorry, something went wrong. Please try again." },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [repoId, snapId],
  );

  const clear = useCallback(() => setMessages([]), []);

  return { messages, loading, send, clear };
}
