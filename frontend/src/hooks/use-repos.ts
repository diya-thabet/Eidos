import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";

export function useRepos() {
  return useQuery({ queryKey: ["repos"], queryFn: api.repos.list });
}

export function useRepo(id: string) {
  return useQuery({ queryKey: ["repos", id], queryFn: () => api.repos.get(id), enabled: !!id });
}

export function useRepoStatus(id: string) {
  return useQuery({
    queryKey: ["repos", id, "status"],
    queryFn: () => api.repos.status(id),
    enabled: !!id,
    refetchInterval: 5000,
  });
}

export function useCreateRepo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.repos.create,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["repos"] }),
  });
}

export function useIngest(repoId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.repos.ingest(repoId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["repos", repoId] }),
  });
}
