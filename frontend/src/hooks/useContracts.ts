import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type {
  ContractDetail,
  ContractSummary,
  TargetLanguage,
  TargetScript,
  TranslationMode,
} from "@/types"


export const contractKeys = {
  all: ["contracts"] as const,
  list: () => [...contractKeys.all, "list"] as const,
  detail: (id: string) => [...contractKeys.all, "detail", id] as const,
}


// A row that hasn't reached a terminal state gets polled — 2s is fast
// enough to feel live during a 15-25s OCR + Stage 1 pipeline without
// hammering the API.
const TERMINAL: ReadonlyArray<ContractSummary["status"]> = ["ready", "failed"]

function pollWhilePending<T extends { status: ContractSummary["status"] }>(
  items: T[] | undefined,
): number | false {
  if (!items?.length) return false
  return items.some((c) => !TERMINAL.includes(c.status)) ? 2000 : false
}


export function useContractList() {
  return useQuery({
    queryKey: contractKeys.list(),
    queryFn: async (): Promise<ContractSummary[]> => {
      const { data } = await api.get<ContractSummary[]>("/api/contracts")
      return data
    },
    // Poll while any row is still being processed, stop when all are
    // ready or failed. Function form so the interval turns off as soon
    // as the last row settles.
    refetchInterval: (query) => pollWhilePending(query.state.data),
  })
}


export function useContract(id: string | undefined) {
  return useQuery({
    queryKey: id ? contractKeys.detail(id) : ["contract-detail-noop"],
    queryFn: async (): Promise<ContractDetail> => {
      const { data } = await api.get<ContractDetail>(`/api/contracts/${id}`)
      return data
    },
    enabled: !!id,
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data) return false
      return TERMINAL.includes(data.status) ? false : 2000
    },
  })
}


/**
 * Re-run OCR + Stage 1 on a contract. Used for retrying a 'failed' row
 * or re-processing after prompt updates. Returns 202 immediately; the
 * list poll picks up the status transitions from there.
 */
export function useReprocessContract() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      await api.post(`/api/contracts/${id}/process`)
      return id
    },
    onSuccess: (id) => {
      // Invalidate list so the poll kicks back in on the row that just
      // flipped away from a terminal status.
      qc.invalidateQueries({ queryKey: contractKeys.list() })
      qc.invalidateQueries({ queryKey: contractKeys.detail(id) })
    },
  })
}


export interface UploadContractInput {
  file: File
  /** BCP-47 short code the worker wants the analysis rendered in. */
  targetLanguage: TargetLanguage
  /** 'native' or 'roman'. Only meaningful when targetLanguage != 'en'. */
  targetScript?: TargetScript
  /** Optional OCR hint if the worker knows the contract's language. */
  sourceLanguage?: TargetLanguage
  /**
   * Sarvam Mayura tone/register:
   *   formal              (default) pure Hindi/Bengali/etc.
   *   modern-colloquial   casual with some English loanwords
   *   classic-colloquial  traditional spoken style
   *   code-mixed          heavy Hinglish/Benglish
   */
  translationMode?: TranslationMode
}


/**
 * Upload a contract file. Sends multipart/form-data — axios handles the
 * boundary + Content-Type when you pass a FormData body.
 *
 * targetLanguage is required: it's the language the worker wants the
 * analysis rendered in, translated from Gemini's English Stage 3 via
 * Sarvam Mayura in the background processor.
 */
export function useUploadContract() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (input: UploadContractInput): Promise<ContractSummary> => {
      const body = new FormData()
      body.append("file", input.file)
      body.append("target_language", input.targetLanguage)
      if (input.targetScript) body.append("target_script", input.targetScript)
      if (input.sourceLanguage) body.append("source_language", input.sourceLanguage)
      if (input.translationMode) body.append("translation_mode", input.translationMode)
      const { data } = await api.post<ContractSummary>(
        "/api/contracts",
        body,
        {
          headers: { "Content-Type": "multipart/form-data" },
        },
      )
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: contractKeys.list() })
    },
  })
}


export function useDeleteContract() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/contracts/${id}`)
      return id
    },
    onSuccess: (id) => {
      qc.setQueryData<ContractSummary[]>(contractKeys.list(), (prev) =>
        prev?.filter((c) => c.id !== id),
      )
      qc.removeQueries({ queryKey: contractKeys.detail(id) })
    },
  })
}
