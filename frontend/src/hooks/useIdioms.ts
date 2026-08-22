import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type {
  Idiom,
  IdiomCreateInput,
  IdiomUpdateInput,
  TargetLanguage,
} from "@/types"


export const idiomKeys = {
  all: ["idioms"] as const,
  list: () => [...idiomKeys.all, "list"] as const,
  detail: (id: string) => [...idiomKeys.all, "detail", id] as const,
}


export function useIdiomList() {
  return useQuery({
    queryKey: idiomKeys.list(),
    queryFn: async (): Promise<Idiom[]> => {
      const { data } = await api.get<Idiom[]>("/api/admin/idioms")
      return data
    },
    staleTime: 30_000,
  })
}


export function useCreateIdiom() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (input: IdiomCreateInput): Promise<Idiom> => {
      const { data } = await api.post<Idiom>("/api/admin/idioms", input)
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: idiomKeys.list() })
    },
  })
}


interface UpdateArgs {
  id: string
  patch: IdiomUpdateInput
}


export function useUpdateIdiom() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, patch }: UpdateArgs): Promise<Idiom> => {
      const { data } = await api.patch<Idiom>(`/api/admin/idioms/${id}`, patch)
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: idiomKeys.list() })
    },
  })
}


export function useDeleteIdiom() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/admin/idioms/${id}`)
      return id
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: idiomKeys.list() })
    },
  })
}


interface TranslationUpsertArgs {
  idiomId: string
  language: TargetLanguage
  translation: string
  notes?: string | null
  is_active?: boolean
}


export function useUpsertIdiomTranslation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      idiomId,
      language,
      translation,
      notes,
      is_active,
    }: TranslationUpsertArgs): Promise<Idiom> => {
      const { data } = await api.put<Idiom>(
        `/api/admin/idioms/${idiomId}/translations/${language}`,
        {
          language,
          translation,
          notes: notes ?? null,
          is_active: is_active ?? true,
        },
      )
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: idiomKeys.list() })
    },
  })
}


interface TranslationDeleteArgs {
  idiomId: string
  language: TargetLanguage
}


export function useDeleteIdiomTranslation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ idiomId, language }: TranslationDeleteArgs) => {
      await api.delete(`/api/admin/idioms/${idiomId}/translations/${language}`)
      return { idiomId, language }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: idiomKeys.list() })
    },
  })
}
