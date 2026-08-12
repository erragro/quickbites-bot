import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { starterKeys } from "@/hooks/useChatStarters"
import type {
  ConvBusinessUnit,
  ConvDataPoint,
  ConvDataPointBinding,
  ConvIssueType,
  ConvTemplate,
} from "@/types"

// Central react-query key factory so cross-tab invalidations stay consistent.
export const convKeys = {
  all: ["conv-admin"] as const,
  businessUnits: () => [...convKeys.all, "bu"] as const,
  issueTypes: () => [...convKeys.all, "it"] as const,
  dataPoints: () => [...convKeys.all, "dp"] as const,
  templates: (itId: string) => [...convKeys.all, "tmpl", itId] as const,
}

// Any mutation to the config invalidates the public chip tree too, so
// the customer-facing UI reflects the change the moment it's saved.
function invalidatePublicTree(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: starterKeys.tree() })
}

// ------------- Business Units -------------

export function useConvBUs() {
  return useQuery({
    queryKey: convKeys.businessUnits(),
    queryFn: async (): Promise<ConvBusinessUnit[]> => {
      const { data } = await api.get<ConvBusinessUnit[]>(
        "/api/admin/conversation/business-units",
      )
      return data
    },
    staleTime: 30_000,
  })
}

interface BUCreate {
  code: string
  name: string
  icon?: string | null
  parent_id?: string | null
  sort_order?: number
}

export function useCreateBU() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: BUCreate): Promise<ConvBusinessUnit> => {
      const { data } = await api.post<ConvBusinessUnit>(
        "/api/admin/conversation/business-units",
        body,
      )
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: convKeys.businessUnits() })
      invalidatePublicTree(qc)
    },
  })
}

interface BUUpdate {
  buId: string
  name?: string
  icon?: string | null
  parent_id?: string | null
  sort_order?: number
  is_active?: boolean
}

export function useUpdateBU() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ buId, ...body }: BUUpdate): Promise<ConvBusinessUnit> => {
      const { data } = await api.patch<ConvBusinessUnit>(
        `/api/admin/conversation/business-units/${buId}`,
        body,
      )
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: convKeys.businessUnits() })
      invalidatePublicTree(qc)
    },
  })
}

export function useDeleteBU() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (buId: string) => {
      await api.delete(`/api/admin/conversation/business-units/${buId}`)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: convKeys.businessUnits() })
      qc.invalidateQueries({ queryKey: convKeys.issueTypes() })
      invalidatePublicTree(qc)
    },
  })
}

// ------------- Issue Types -------------

export function useConvIssueTypes() {
  return useQuery({
    queryKey: convKeys.issueTypes(),
    queryFn: async (): Promise<ConvIssueType[]> => {
      const { data } = await api.get<ConvIssueType[]>(
        "/api/admin/conversation/issue-types",
      )
      return data
    },
    staleTime: 30_000,
  })
}

interface ITCreate {
  business_unit_id: string
  code: string
  name: string
  description?: string | null
  icon?: string | null
  routes_to_intent?: string | null
  sort_order?: number
}

export function useCreateIssueType() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: ITCreate): Promise<ConvIssueType> => {
      const { data } = await api.post<ConvIssueType>(
        "/api/admin/conversation/issue-types",
        body,
      )
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: convKeys.issueTypes() })
      invalidatePublicTree(qc)
    },
  })
}

interface ITUpdate {
  itId: string
  business_unit_id?: string
  name?: string
  description?: string | null
  icon?: string | null
  routes_to_intent?: string | null
  sort_order?: number
  is_active?: boolean
}

export function useUpdateIssueType() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ itId, ...body }: ITUpdate): Promise<ConvIssueType> => {
      const { data } = await api.patch<ConvIssueType>(
        `/api/admin/conversation/issue-types/${itId}`,
        body,
      )
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: convKeys.issueTypes() })
      invalidatePublicTree(qc)
    },
  })
}

export function useDeleteIssueType() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (itId: string) => {
      await api.delete(`/api/admin/conversation/issue-types/${itId}`)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: convKeys.issueTypes() })
      invalidatePublicTree(qc)
    },
  })
}

interface ReplaceBindingsArgs {
  itId: string
  bindings: ConvDataPointBinding[]
}

export function useReplaceBindings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ itId, bindings }: ReplaceBindingsArgs): Promise<ConvIssueType> => {
      const { data } = await api.put<ConvIssueType>(
        `/api/admin/conversation/issue-types/${itId}/data-points`,
        { bindings },
      )
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: convKeys.issueTypes() })
    },
  })
}

// ------------- Data Points (read-only) -------------

export function useConvDataPoints() {
  return useQuery({
    queryKey: convKeys.dataPoints(),
    queryFn: async (): Promise<ConvDataPoint[]> => {
      const { data } = await api.get<ConvDataPoint[]>(
        "/api/admin/conversation/data-points",
      )
      return data
    },
    staleTime: 5 * 60 * 1000,
  })
}

// ------------- Templates -------------

export function useConvTemplates(itId: string | undefined) {
  return useQuery({
    queryKey: itId ? convKeys.templates(itId) : ["tmpl-noop"],
    queryFn: async (): Promise<ConvTemplate[]> => {
      const { data } = await api.get<ConvTemplate[]>(
        `/api/admin/conversation/issue-types/${itId}/templates`,
      )
      return data
    },
    enabled: !!itId,
  })
}

interface TemplateCreate {
  itId: string
  template: string
  weight?: number
  is_active?: boolean
}

export function useCreateTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ itId, ...body }: TemplateCreate): Promise<ConvTemplate> => {
      const { data } = await api.post<ConvTemplate>(
        `/api/admin/conversation/issue-types/${itId}/templates`,
        body,
      )
      return data
    },
    onSuccess: (_res, { itId }) => {
      qc.invalidateQueries({ queryKey: convKeys.templates(itId) })
    },
  })
}

interface TemplateUpdate {
  tplId: string
  itId: string
  template?: string
  weight?: number
  is_active?: boolean
}

export function useUpdateTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ tplId, template, weight, is_active }: TemplateUpdate): Promise<ConvTemplate> => {
      const { data } = await api.patch<ConvTemplate>(
        `/api/admin/conversation/templates/${tplId}`,
        { template, weight, is_active },
      )
      return data
    },
    onSuccess: (_res, { itId }) => {
      qc.invalidateQueries({ queryKey: convKeys.templates(itId) })
    },
  })
}

export function useDeleteTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ tplId, itId: _itId }: { tplId: string; itId: string }) => {
      await api.delete(`/api/admin/conversation/templates/${tplId}`)
    },
    onSuccess: (_res, { itId }) => {
      qc.invalidateQueries({ queryKey: convKeys.templates(itId) })
    },
  })
}
