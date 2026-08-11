import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type { AccessLevel, AdminUser, ModuleInfo } from "@/types"

export const adminKeys = {
  all: ["admin"] as const,
  users: () => [...adminKeys.all, "users"] as const,
  modules: () => [...adminKeys.all, "modules"] as const,
}

// ------------------------------- reads -------------------------------

export function useAdminUsers() {
  return useQuery({
    queryKey: adminKeys.users(),
    queryFn: async (): Promise<AdminUser[]> => {
      const { data } = await api.get<AdminUser[]>("/api/admin/users")
      return data
    },
    staleTime: 30_000,
  })
}

export function useAdminModules() {
  return useQuery({
    queryKey: adminKeys.modules(),
    queryFn: async (): Promise<ModuleInfo[]> => {
      const { data } = await api.get<ModuleInfo[]>("/api/admin/modules")
      return data
    },
    staleTime: 60_000,
  })
}

// ------------------------------ mutations ----------------------------

interface GrantArgs {
  userId: string
  moduleId: string
  accessLevel: AccessLevel
}

export function useGrantAccess() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ userId, moduleId, accessLevel }: GrantArgs): Promise<AdminUser> => {
      const { data } = await api.post<AdminUser>(
        `/api/admin/users/${userId}/access`,
        { module_id: moduleId, access_level: accessLevel },
      )
      return data
    },
    onSuccess: (updated) => {
      // Splice the updated user back into the list cache.
      qc.setQueryData<AdminUser[]>(adminKeys.users(), (prev) =>
        prev?.map((u) => (u.id === updated.id ? updated : u)),
      )
    },
  })
}

interface RevokeArgs {
  userId: string
  moduleId: string
}

export function useRevokeAccess() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ userId, moduleId }: RevokeArgs): Promise<AdminUser> => {
      const { data } = await api.delete<AdminUser>(
        `/api/admin/users/${userId}/access/${moduleId}`,
      )
      return data
    },
    onSuccess: (updated) => {
      qc.setQueryData<AdminUser[]>(adminKeys.users(), (prev) =>
        prev?.map((u) => (u.id === updated.id ? updated : u)),
      )
    },
  })
}

interface UpdateArgs {
  userId: string
  is_active?: boolean
  is_super_admin?: boolean
}

export function useUpdateUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ userId, ...body }: UpdateArgs): Promise<AdminUser> => {
      const { data } = await api.patch<AdminUser>(`/api/admin/users/${userId}`, body)
      return data
    },
    onSuccess: (updated) => {
      qc.setQueryData<AdminUser[]>(adminKeys.users(), (prev) =>
        prev?.map((u) => (u.id === updated.id ? updated : u)),
      )
    },
  })
}

interface RegisterModuleArgs {
  key: string
  name: string
  description?: string
  icon?: string
  path: string
  sort_order?: number
}

export function useRegisterModule() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: RegisterModuleArgs): Promise<ModuleInfo> => {
      const { data } = await api.post<ModuleInfo>("/api/admin/modules", body)
      return data
    },
    onSuccess: async () => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: adminKeys.modules() }),
        qc.invalidateQueries({ queryKey: ["modules"] }),
      ])
    },
  })
}
