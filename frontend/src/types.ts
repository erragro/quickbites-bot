// API DTOs — kept in sync with app/schemas.py + app/sessions/schemas.py + app/auth/schemas.py.
// Any change to a backend Pydantic model should be mirrored here.

export interface User {
  id: string
  email: string
  is_active: boolean
  is_super_admin?: boolean
  created_at: string
}

export type AccessLevel = "view" | "edit" | "admin"

export interface ModuleInfo {
  id: string
  key: string
  name: string
  description: string | null
  icon: string | null
  path: string
  is_system: boolean
  sort_order: number
  access_level: AccessLevel | null
}

export interface UserModuleAccessDTO {
  module_id: string
  module_key: string
  module_name: string
  access_level: AccessLevel
  granted_at: string
  granted_by: string | null
}

export interface AdminUser {
  id: string
  email: string
  is_active: boolean
  is_super_admin: boolean
  created_at: string
  module_accesses: UserModuleAccessDTO[]
}

// ------- Conversation Studio (chip-tap) types -------

export interface IssueTypeChip {
  id: string
  code: string
  name: string
  description: string | null
  icon: string | null
  sort_order: number
}

export interface BusinessUnitTree {
  id: string
  code: string
  name: string
  icon: string | null
  sort_order: number
  issue_types: IssueTypeChip[]
  children: BusinessUnitTree[]
}

export interface ChatStartersResponse {
  business_units: BusinessUnitTree[]
}

export interface SelectIssueRequest {
  issue_type_id: string
  customer_id?: number
  order_id?: number
}

export interface SelectIssueResponse {
  session_id: string
  issue_type_id: string
  business_unit_id: string
  acknowledgment: string
  resolved_data_points: string[]
}

// ------- Conversation Studio admin DTOs -------

export interface ConvBusinessUnit {
  id: string
  code: string
  name: string
  icon: string | null
  parent_id: string | null
  sort_order: number
  is_active: boolean
  created_at: string
}

export interface ConvDataPoint {
  id: string
  key: string
  name: string
  description: string | null
  fetcher_ref: string
  is_system: boolean
  created_at: string
}

export interface ConvDataPointBinding {
  data_point_id: string
  is_required: boolean
  sort_order: number
}

export interface ConvIssueType {
  id: string
  business_unit_id: string
  code: string
  name: string
  description: string | null
  icon: string | null
  routes_to_intent: string | null
  sort_order: number
  is_active: boolean
  data_points: ConvDataPointBinding[]
}

export interface ConvTemplate {
  id: string
  issue_type_id: string
  template: string
  weight: number
  is_active: boolean
  created_at: string
}

export interface AuthToken {
  access_token: string
  token_type: string
  expires_in_minutes: number
}

export interface SessionSummary {
  session_id: string
  title: string | null
  opened_at: string
  closed_at: string | null
}

export interface Turn {
  turn_no: number
  role: "customer" | "bot" | string
  message: string | null
  actions: unknown[] | Record<string, unknown> | null
  created_at: string
}

export interface SessionDetail {
  session_id: string
  user_id: string | null
  title: string | null
  opened_at: string
  closed_at: string | null
  close_reason: string | null
  turns: Turn[]
}

export interface ChatMessageResponse {
  session_id: string
  turn_no: number
  bot_message: string
  actions: Record<string, unknown>[]
  detected_language: string | null
  route: string | null
  escalation_group: string | null
}

export interface ApiError {
  detail: string | { msg: string; loc?: string[] }[]
  status?: number
}
