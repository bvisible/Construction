import { apiGet, apiPost, apiPatch, apiDelete } from '@/shared/lib/api';

export interface Schedule {
  id: string;
  project_id: string;
  name: string;
  description: string;
  start_date: string | null;
  end_date: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface Activity {
  id: string;
  schedule_id: string;
  parent_id: string | null;
  name: string;
  description: string;
  wbs_code: string;
  start_date: string;
  end_date: string;
  duration_days: number;
  progress_pct: number;
  status: string;
  activity_type: string;
  dependencies: Array<{ activity_id: string; type: string; lag_days: number }>;
  resources: Array<{ name: string; type: string; allocation_pct: number }>;
  boq_position_ids: string[];
  /** BIM elements pinned to this activity for 4D scheduling.  Backend
   *  populates this from the `Activity.bim_element_ids` JSON column. */
  bim_element_ids?: string[] | null;
  color: string;
  sort_order: number;
  /** Activity metadata passthrough. BOQ-generated activities carry
   *  `duration_source` / `duration_method` = "estimated_fallback" here when
   *  the duration was estimated from unit-based production rates rather than
   *  real labor data. */
  metadata?: Record<string, unknown> | null;
}

export interface WorkOrder {
  id: string;
  activity_id: string;
  assembly_id: string | null;
  boq_position_id: string | null;
  code: string;
  description: string;
  assigned_to: string;
  planned_start: string | null;
  planned_end: string | null;
  actual_start: string | null;
  actual_end: string | null;
  planned_cost: number;
  actual_cost: number;
  status: string;
}

export interface GanttData {
  activities: Activity[];
  summary: {
    total_activities: number;
    completed: number;
    in_progress: number;
    delayed: number;
  };
}

export interface CPMActivityResult {
  activity_id: string;
  name: string;
  duration_days: number;
  early_start: number;
  early_finish: number;
  late_start: number;
  late_finish: number;
  total_float: number;
  is_critical: boolean;
}

export interface CriticalPathResponse {
  schedule_id: string;
  project_duration_days: number;
  critical_path: CPMActivityResult[];
  all_activities: CPMActivityResult[];
}

export interface RiskAnalysisResponse {
  schedule_id: string;
  deterministic_days: number;
  p50_days: number;
  p80_days: number;
  p95_days: number;
  mean_days: number;
  std_dev_days: number;
  risk_buffer_days: number;
  activity_risks: Array<{
    activity_id: string;
    name: string;
    duration_days: number;
    optimistic: number;
    most_likely: number;
    pessimistic: number;
    expected: number;
    std_dev: number;
    is_critical: boolean;
  }>;
}

/**
 * Scalar earned-value (EVM) metrics for a schedule at a data date.
 *
 * Mirrors the backend ``EvmSummaryResponse``. Money fields arrive as the
 * platform Decimal-as-string wire contract (decode via `shared/lib/money.ts`);
 * the dimensionless indices and the CPI-method forecast are `number | null`
 * (`null` when the schedule is not cost-loaded or a denominator is zero).
 */
export interface EvmSummary {
  schedule_id: string;
  as_of_date: string;
  /** Planned value (BCWS), time-phased to the data date. Decimal string. */
  planned_value: string;
  /** Earned value (BCWP). Decimal string. */
  earned_value: string;
  /** Actual cost (ACWP). Decimal string. */
  actual_cost: string;
  /** Budget at completion (Σ planned cost). Decimal string. */
  budget_at_completion: string;
  /** Schedule variance = EV - PV. Decimal string. */
  schedule_variance: string;
  /** Cost variance = EV - AC. Decimal string. */
  cost_variance: string;
  /** Estimate at completion = BAC / CPI. Decimal string or null. */
  estimate_at_completion: string | null;
  /** Estimate to complete = EAC - AC. Decimal string or null. */
  estimate_to_complete: string | null;
  /** Variance at completion = BAC - EAC. Decimal string or null. */
  variance_at_completion: string | null;
  /** Schedule performance index = EV / PV. */
  spi: number | null;
  /** Cost performance index = EV / AC. */
  cpi: number | null;
  has_cost_data: boolean;
}

/**
 * 4D snapshot: per-BIM-element status on a given as-of date. ``elements`` maps
 * each resolved element id to its derived status
 * (not_started / in_progress / completed / delayed / ahead_of_schedule).
 */
export interface ScheduleSnapshot {
  schedule_id: string;
  as_of_date: string;
  model_version_id: string | null;
  elements: Record<string, string>;
}

/** Defensive unwrap: handle both plain array and paginated {items, total} responses. */
function unwrapList<T>(res: T[] | { items: T[] }): T[] {
  return Array.isArray(res) ? res : res.items ?? [];
}

export const scheduleApi = {
  // Schedules
  listSchedules: (projectId: string) =>
    apiGet<Schedule[] | { items: Schedule[] }>(`/v1/schedule/schedules/?project_id=${projectId}`).then(unwrapList),
  getSchedule: (id: string) => apiGet<Schedule>(`/v1/schedule/schedules/${id}`),
  createSchedule: (data: { project_id: string; name: string; description?: string; start_date?: string; end_date?: string }) =>
    apiPost<Schedule>('/v1/schedule/schedules/', data),
  updateSchedule: (id: string, data: { name?: string; description?: string; start_date?: string; end_date?: string; status?: string }) =>
    apiPatch<Schedule>(`/v1/schedule/schedules/${id}`, data),

  // Activities
  getGantt: (scheduleId: string) =>
    apiGet<GanttData>(`/v1/schedule/schedules/${scheduleId}/gantt/`),
  createActivity: (scheduleId: string, data: Partial<Activity>) =>
    apiPost<Activity>(`/v1/schedule/schedules/${scheduleId}/activities/`, data),
  updateActivity: (activityId: string, data: Partial<Activity>) =>
    apiPatch<Activity>(`/v1/schedule/activities/${activityId}`, data),
  deleteActivity: (activityId: string) =>
    apiDelete(`/v1/schedule/activities/${activityId}`),
  clearActivities: (scheduleId: string) =>
    apiDelete<{ schedule_id: string; deleted: number }>(
      `/v1/schedule/schedules/${scheduleId}/activities/`,
    ),
  linkPosition: (activityId: string, positionId: string) =>
    apiPost(`/v1/schedule/activities/${activityId}/link-position/`, { boq_position_id: positionId }),
  updateProgress: (activityId: string, progressPct: number) =>
    apiPatch(`/v1/schedule/activities/${activityId}/progress/`, { progress_pct: progressPct }),

  // CPM & BOQ Generation
  generateFromBOQ: (scheduleId: string, boqId: string, totalProjectDays?: number) =>
    apiPost<Activity[]>(`/v1/schedule/schedules/${scheduleId}/generate-from-boq/`, {
      boq_id: boqId,
      ...(totalProjectDays != null ? { total_project_days: totalProjectDays } : {}),
    }),
  calculateCPM: (scheduleId: string) =>
    apiPost<CriticalPathResponse>(`/v1/schedule/schedules/${scheduleId}/calculate-cpm/`),
  getRiskAnalysis: (scheduleId: string) =>
    apiGet<RiskAnalysisResponse>(`/v1/schedule/schedules/${scheduleId}/risk-analysis/`),

  // EVM (earned value) + 4D snapshot
  /** Scalar EVM rollup (PV/EV/AC, SPI/CPI, EAC) for a schedule at a data date. */
  getEvmSummary: (scheduleId: string, asOfDate?: string) =>
    apiGet<EvmSummary>(
      `/v1/schedule/schedules/${scheduleId}/evm-summary/${
        asOfDate ? `?as_of_date=${encodeURIComponent(asOfDate)}` : ''
      }`,
    ),
  /** 4D element-status snapshot for a schedule at a data date (v2 surface). */
  getSnapshot: (scheduleId: string, params?: { asOfDate?: string; modelVersionId?: string }) => {
    const qs = new URLSearchParams();
    if (params?.asOfDate) qs.set('as_of_date', params.asOfDate);
    if (params?.modelVersionId) qs.set('model_version_id', params.modelVersionId);
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return apiGet<ScheduleSnapshot>(`/v2/schedules/${scheduleId}/snapshot${suffix}`);
  },

  // Work Orders
  // The backend /work-orders/ endpoint requires schedule_id and has no
  // activity_id filter, so schedule_id is mandatory here to avoid a 422.
  listWorkOrders: (params: { schedule_id: string }) =>
    apiGet<WorkOrder[] | { items: WorkOrder[] }>(`/v1/schedule/work-orders/?${new URLSearchParams(params as Record<string, string>)}`).then(unwrapList),
  createWorkOrder: (activityId: string, data: Partial<WorkOrder>) =>
    apiPost<WorkOrder>(`/v1/schedule/activities/${activityId}/work-orders/`, data),
  updateWorkOrder: (id: string, data: Partial<WorkOrder>) =>
    apiPatch<WorkOrder>(`/v1/schedule/work-orders/${id}`, data),
};
