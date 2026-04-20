import { useQuery, useMutation } from "@tanstack/react-query";
import { api, type HealthCheckRequest } from "@/lib/api-client";

export function useHealthRules(repoId: string, snapId: string) {
  return useQuery({
    queryKey: ["health-rules", repoId, snapId],
    queryFn: () => api.health.rules(repoId, snapId),
    enabled: !!repoId && !!snapId,
  });
}

export function useHealthCheck(repoId: string, snapId: string) {
  return useMutation({
    mutationFn: (body: HealthCheckRequest) => api.health.check(repoId, snapId, body),
  });
}
