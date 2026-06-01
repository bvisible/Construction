/**
 * API helpers for Requests for Information (RFI).
 *
 * All endpoints are prefixed with /v1/rfi/.
 */

import { apiGet, apiPost } from '@/shared/lib/api';

/* ── Types ─────────────────────────────────────────────────────────────── */

export type RFIStatus = 'draft' | 'open' | 'answered' | 'closed' | 'void';

export type RFIPriority = 'low' | 'normal' | 'high' | 'critical';

/**
 * Common construction disciplines for an RFI. Kept as a constant so the
 * picker and the filter dropdown stay in lockstep.
 *
 * The backend column is free-form `String(50)` so future disciplines can
 * land without a migration — this list is only what the frontend offers.
 */
export const RFI_DISCIPLINES = [
  'architectural',
  'structural',
  'mep',
  'electrical',
  'plumbing',
  'civil',
  'landscape',
] as const;

export type RFIDiscipline = (typeof RFI_DISCIPLINES)[number];

export interface RFI {
  id: string;
  project_id: string;
  rfi_number: string;
  subject: string;
  question: string;
  official_response: string | null;
  status: RFIStatus;
  raised_by: string;
  assigned_to: string | null;
  ball_in_court: string | null;
  responded_by: string | null;
  responded_at: string | null;
  cost_impact: boolean;
  cost_impact_value: string | null;
  schedule_impact: boolean;
  schedule_impact_days: number | null;
  date_required: string | null;
  response_due_date: string | null;
  linked_drawing_ids: string[];
  change_order_id: string | null;
  created_by: string | null;
  priority: RFIPriority | null;
  /**
   * Discipline — typically one of {@link RFI_DISCIPLINES} but kept as a
   * raw string here because the backend column is free-form and might
   * already carry custom values from other clients.
   */
  discipline: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  is_overdue: boolean;
  days_open: number;
}

export interface RFIFilters {
  project_id?: string;
  status?: RFIStatus | '';
  search?: string;
  offset?: number;
  limit?: number;
}

export interface RFIStats {
  total: number;
  by_status: Record<string, number>;
  open: number;
  overdue: number;
  avg_days_to_response: number | null;
  cost_impact_count: number;
  schedule_impact_count: number;
}

export interface CreateRFIPayload {
  project_id: string;
  subject: string;
  question: string;
  ball_in_court?: string;
  assigned_to?: string;
  response_due_date?: string;
  date_required?: string;
  cost_impact?: boolean;
  cost_impact_value?: string;
  schedule_impact?: boolean;
  schedule_impact_days?: number;
  linked_drawing_ids?: string[];
  priority?: RFIPriority;
  discipline?: string;
}

export interface RespondRFIPayload {
  official_response: string;
}

/* ── API Functions ─────────────────────────────────────────────────────── */

export async function getRFI(id: string): Promise<RFI> {
  // The route is GET /{rfi_id} with NO trailing slash (router.py) and the
  // app runs with redirect_slashes=False, so a trailing slash here 404s
  // and the detail page permanently shows "RFI not found".
  return apiGet<RFI>(`/v1/rfi/${id}`);
}

export async function fetchRFIs(filters?: RFIFilters): Promise<RFI[]> {
  const params = new URLSearchParams();
  if (filters?.project_id) params.set('project_id', filters.project_id);
  if (filters?.status) params.set('status', filters.status);
  if (filters?.search && filters.search.trim()) params.set('search', filters.search.trim());
  if (typeof filters?.offset === 'number') params.set('offset', String(filters.offset));
  if (typeof filters?.limit === 'number') params.set('limit', String(filters.limit));
  const qs = params.toString();
  return apiGet<RFI[]>(`/v1/rfi/${qs ? `?${qs}` : ''}`);
}

export async function fetchRFIStats(projectId: string): Promise<RFIStats> {
  return apiGet<RFIStats>(`/v1/rfi/stats/?project_id=${encodeURIComponent(projectId)}`);
}

export async function createRFI(data: CreateRFIPayload): Promise<RFI> {
  return apiPost<RFI>('/v1/rfi/', data);
}

export async function respondToRFI(id: string, data: RespondRFIPayload): Promise<RFI> {
  return apiPost<RFI>(`/v1/rfi/${id}/respond/`, data);
}

export async function closeRFI(id: string): Promise<RFI> {
  return apiPost<RFI>(`/v1/rfi/${id}/close/`);
}
