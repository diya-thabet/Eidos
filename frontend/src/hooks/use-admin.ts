import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";

export function useAdminSystem() {
  return useQuery({ queryKey: ["admin", "system"], queryFn: api.admin.system });
}

export function useAdminUsers() {
  return useQuery({ queryKey: ["admin", "users"], queryFn: api.admin.users });
}

export function useAdminPlans() {
  return useQuery({ queryKey: ["admin", "plans"], queryFn: api.admin.plans });
}
