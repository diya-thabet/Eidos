import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";

export function useSymbols(repoId: string, snapId: string, params?: string) {
  return useQuery({
    queryKey: ["symbols", repoId, snapId, params],
    queryFn: () => api.analysis.symbols(repoId, snapId, params),
    enabled: !!repoId && !!snapId,
  });
}

export function useOverview(repoId: string, snapId: string) {
  return useQuery({
    queryKey: ["overview", repoId, snapId],
    queryFn: () => api.analysis.overview(repoId, snapId),
    enabled: !!repoId && !!snapId,
  });
}

export function useGraphNeighborhood(repoId: string, snapId: string, fq: string) {
  return useQuery({
    queryKey: ["graph", repoId, snapId, fq],
    queryFn: () => api.analysis.graph(repoId, snapId, fq),
    enabled: !!repoId && !!snapId && !!fq,
  });
}
