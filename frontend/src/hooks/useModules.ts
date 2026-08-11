import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type { ModuleInfo } from "@/types"

export const moduleKeys = {
  all: ["modules"] as const,
  list: () => [...moduleKeys.all, "list"] as const,
}

export function useModules() {
  return useQuery({
    queryKey: moduleKeys.list(),
    queryFn: async (): Promise<ModuleInfo[]> => {
      const { data } = await api.get<ModuleInfo[]>("/api/modules")
      return data
    },
    staleTime: 60_000,
  })
}
