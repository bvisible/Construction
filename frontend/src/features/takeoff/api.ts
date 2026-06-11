/**
 * Takeoff Measurements API client.
 *
 * Mirrors backend endpoints at /v1/takeoff/measurements/*.
 */

import { apiGet, apiPost, apiPatch, apiDelete } from '@/shared/lib/api';
import { isModuleLoaded } from '@/shared/lib/moduleProbe';

/* ── Types ────────────────────────────────────────────────────────────── */

export interface MeasurementPoint {
  x: number;
  y: number;
}

export interface MeasurementCreate {
  project_id: string;
  document_id?: string | null;
  page: number;
  type: string;
  group_name?: string;
  group_color?: string;
  annotation?: string | null;
  points: MeasurementPoint[];
  measurement_value?: number | null;
  measurement_unit?: string;
  depth?: number | null;
  volume?: number | null;
  perimeter?: number | null;
  count_value?: number | null;
  scale_pixels_per_unit?: number | null;
  linked_boq_position_id?: string | null;
  metadata?: Record<string, unknown>;
}

export interface MeasurementResponse {
  id: string;
  project_id: string;
  document_id: string | null;
  page: number;
  type: string;
  group_name: string;
  group_color: string;
  annotation: string | null;
  points: MeasurementPoint[];
  measurement_value: number | null;
  measurement_unit: string;
  depth: number | null;
  volume: number | null;
  perimeter: number | null;
  count_value: number | null;
  scale_pixels_per_unit: number | null;
  linked_boq_position_id: string | null;
  metadata: Record<string, unknown>;
  created_by: string;
  created_at: string;
  updated_at: string;
  /** Provenance of the measurement (issue #194). 'ai_plan_read' marks a
   *  vision-LLM proposal; 'manual' is a human-drawn measurement. */
  source?: string;
  /** AI confidence 0..1, present only on AI-sourced rows (null otherwise). */
  confidence?: number | null;
  /** Review state: 'proposed' (unconfirmed AI suggestion), 'confirmed', or
   *  'rejected'. Manual measurements default to 'confirmed'. */
  review_status?: string;
}

/** One unconfirmed measurement proposed by offline vector recognition (#194). */
export interface RecognizeCandidate {
  type: 'area' | 'distance' | 'count';
  points: MeasurementPoint[];
  value: number | null;
  dimension: string;
  count?: number | null;
  confidence: number;
  reason: string;
}

export interface RecognizeResult {
  candidates: RecognizeCandidate[];
  page: number;
  source: string;
  notes: string | null;
}

/* ── Vision-LLM plan reading (issue #194) ──────────────────────────────────
 * An ADDITIONAL, higher-quality suggestion source alongside the offline
 * Recognize tool. Bring-your-own-key, cost-capped, and human-confirmed: a run
 * only produces ``proposed`` measurements; the user accepts/rejects each, and
 * the server recomputes the billed number. Nothing is auto-applied. */

export type PlanReadMode = 'scale' | 'rooms' | 'symbols' | 'full';

export interface PlanReadMeta {
  confidence_high_threshold: number;
  confidence_medium_threshold: number;
  vision_providers: string[];
  max_polygon_vertices: number;
  // Money on the wire is a Decimal-rendered string (v3 §10); coerce with
  // Number() at any display site.
  max_cost_usd: number | string;
  rolling_spend_usd: number | string;
  modes: PlanReadMode[];
  /** False when no vision-capable AI key is configured. The "Read plan with
   *  AI" action is hidden / disabled in that case; the offline Recognize tool
   *  is unaffected (graceful degradation). */
  vision_available: boolean;
  provider: string | null;
  model_used: string | null;
  /** A human-readable reason when vision_available is false. */
  reason: string | null;
}

export interface AiTakeoffRun {
  id: string;
  status: string;
  project_id: string;
  document_id: string | null;
  page: number;
  mode: string;
  provider: string | null;
  model_used: string | null;
  total_tokens: number;
  // Decimal-rendered string on the wire (v3 §10); Number() to display.
  cost_usd_estimate: number | string;
  duration_ms: number;
  proposal_count: number;
  accepted_count: number;
  validation_report: Record<string, unknown> | null;
  failure_reason: string | null;
  created_at: string | null;
}

export interface PlanReadStartRequest {
  project_id: string;
  document_id: string;
  page: number;
  scale_pixels_per_unit?: number | null;
  mode?: PlanReadMode;
  do_cost_match?: boolean;
}

export interface PlanReadAcceptResult {
  confirmed: number;
  skipped: number;
  blocked: number;
  measurement_ids: string[];
}

export interface PlanReadRejectResult {
  rejected: number;
  skipped: number;
  measurement_ids: string[];
}

export interface MeasurementSummary {
  total_measurements: number;
  by_type: Record<string, number>;
  by_group: Record<string, number>;
}

export interface TakeoffDocumentResponse {
  id: string;
  filename: string;
  pages: number;
  size_bytes: number;
  status: string;
  project_id?: string | null;
  uploaded_at: string | null;
}

/* ── Revision compare (Item 17) ────────────────────────────────────────── */

/** One measurement-level change between two takeoff documents. */
export interface TakeoffMeasurementDiffRow {
  change_type: 'added' | 'removed' | 'modified' | 'unchanged';
  measurement_id: string;
  type: string;
  group_name: string;
  page: number;
  label: string | null;
  old_value: number | null;
  new_value: number | null;
  measurement_unit: string | null;
  linked_boq_position_id: string | null;
  /** Signed Decimal string in the project base currency, or null when the
   *  measurement is unlinked / unpriced. */
  cost_impact: string | null;
  cost_currency: string | null;
}

export interface TakeoffCompareResponse {
  project_id: string;
  from_document_id: string;
  to_document_id: string;
  measurement_rows: TakeoffMeasurementDiffRow[];
  summary: {
    measurements: Record<'added' | 'removed' | 'modified' | 'unchanged', number>;
    net_cost_impact: string | null;
    cost_currency: string | null;
    from_measurement_count: number;
    to_measurement_count: number;
  };
}

/** The draft variation request minted from a PDF revision-compare delta. */
export interface CreateVariationFromCompareResult {
  variation_request_id: string;
  code: string;
  estimated_cost_impact: string;
  currency: string;
}

// //// NEOFFICE PATCH — accept raw or proxy/paginated list payloads.
// Osiris can expose OCE responses through the Frappe proxy, and some upstream
// endpoints moved from raw arrays to paginated objects. Keep list consumers
// defensive so a harmless response envelope cannot crash React with `.map`.
export function normalizeListResponse<T>(payload: unknown, keys: string[] = []): T[] {
  if (Array.isArray(payload)) return payload as T[];
  if (!payload || typeof payload !== 'object') return [];

  const obj = payload as Record<string, unknown>;
  const orderedKeys = [...keys, 'items', 'data', 'results', 'rows', 'message'];
  const nestedKeys = ['items', 'data', 'results', 'rows'];

  for (const key of orderedKeys) {
    const value = obj[key];
    if (Array.isArray(value)) return value as T[];
    if (value && typeof value === 'object') {
      const nestedObj = value as Record<string, unknown>;
      for (const nestedKey of nestedKeys) {
        const nested = nestedObj[nestedKey];
        if (Array.isArray(nested)) return nested as T[];
      }
    }
  }

  return [];
}
// //// END NEOFFICE PATCH

/* ── API functions ────────────────────────────────────────────────────── */

export const takeoffApi = {
  /** List measurements for a project, optionally filtered by document.
   *  /markups page calls this on mount; returns empty when oe_takeoff
   *  is disabled so the request never 404-logs to the network panel. */
  list: async (projectId: string, documentId?: string): Promise<MeasurementResponse[]> => {
    if (!(await isModuleLoaded('oe_takeoff'))) return [];
    let url = `/v1/takeoff/measurements/?project_id=${projectId}`;
    if (documentId) url += `&document_id=${encodeURIComponent(documentId)}`;
    const payload = await apiGet<unknown>(url);
    return normalizeListResponse<MeasurementResponse>(payload, ['measurements']);
  },

  /** Create a single measurement. */
  create: (data: MeasurementCreate) =>
    apiPost<MeasurementResponse>('/v1/takeoff/measurements/', data),

  /** Bulk create measurements (up to 500). */
  bulkCreate: (measurements: MeasurementCreate[]) =>
    apiPost<unknown>('/v1/takeoff/measurements/bulk/', { measurements })
      .then((payload) => normalizeListResponse<MeasurementResponse>(payload, ['measurements'])),

  /** Update a measurement. */
  update: (id: string, data: Partial<MeasurementCreate>) =>
    apiPatch<MeasurementResponse>(`/v1/takeoff/measurements/${id}`, data),

  /** Delete a measurement. */
  delete: (id: string) =>
    apiDelete(`/v1/takeoff/measurements/${id}`),

  /** Link a measurement to a BOQ position. */
  linkToBoq: (id: string, boqPositionId: string) =>
    apiPost<MeasurementResponse>(`/v1/takeoff/measurements/${id}/link-to-boq/`, {
      boq_position_id: boqPositionId,
    }),

  /** Recognize candidate measurements from a page's vector layer (offline,
   *  issue #194). Returns confidence-scored area/length/count candidates that
   *  the user confirms on the canvas; nothing is persisted server-side. */
  recognize: (docId: string, page: number, scalePixelsPerUnit?: number) => {
    const sp = scalePixelsPerUnit && scalePixelsPerUnit > 0 ? scalePixelsPerUnit : 0;
    return apiPost<RecognizeResult>(
      `/v1/takeoff/documents/${encodeURIComponent(docId)}/recognize/?page=${page}&scale_pixels_per_unit=${sp}`,
      {},
    );
  },

  /* ── Vision-LLM plan reading (issue #194) ─────────────────────────────── */
  planRead: {
    /** Thresholds, vision availability, caps, and rolling spend. Returns a
     *  graceful "vision_available: false" payload (never throws) when the
     *  module is disabled so the viewer can hide the action without errors. */
    meta: async (): Promise<PlanReadMeta | null> => {
      if (!(await isModuleLoaded('oe_takeoff'))) return null;
      return apiGet<PlanReadMeta>('/v1/takeoff/plan-read/meta');
    },

    /** Start a vision plan-read run for one page. 400 when no vision key is
     *  configured, the model is text-only, or the cost cap would be exceeded. */
    start: (body: PlanReadStartRequest) =>
      apiPost<AiTakeoffRun>('/v1/takeoff/plan-read/', body),

    /** Poll a run's FSM state. */
    getRun: (runId: string) =>
      apiGet<AiTakeoffRun>(`/v1/takeoff/plan-read/runs/${encodeURIComponent(runId)}`),

    /** List the unconfirmed (proposed) measurements minted by a run. */
    proposals: (runId: string) =>
      apiGet<unknown>(
        `/v1/takeoff/plan-read/runs/${encodeURIComponent(runId)}/proposals`,
      ).then((payload) =>
        normalizeListResponse<MeasurementResponse>(payload, ['proposals', 'measurements']),
      ),

    /** Confirm selected / above-threshold proposals into billed measurements.
     *  A self-intersecting proposal is blocked (redraw first). */
    accept: (
      runId: string,
      body: { measurement_ids?: string[] | null; min_confidence?: number | null },
    ) =>
      apiPost<PlanReadAcceptResult>(
        `/v1/takeoff/plan-read/runs/${encodeURIComponent(runId)}/accept`,
        body,
      ),

    /** Reject selected proposals and remove them from future reloads. */
    reject: (
      runId: string,
      body: { measurement_ids?: string[] | null },
    ) =>
      apiPost<PlanReadRejectResult>(
        `/v1/takeoff/plan-read/runs/${encodeURIComponent(runId)}/reject`,
        body,
      ),
  },

  /** Get measurement summary stats for a project. */
  summary: (projectId: string) =>
    apiGet<MeasurementSummary>(`/v1/takeoff/measurements/summary/?project_id=${projectId}`),

  /** Export measurements as CSV or JSON. */
  export: (projectId: string, format: 'csv' | 'json' = 'json') =>
    apiGet<unknown>(`/v1/takeoff/measurements/export/?project_id=${projectId}&format=${format}`),

  /** List uploaded takeoff documents for a project.
   *  Returns empty when the optional `oe_takeoff` module is disabled. */
  listDocuments: async (projectId?: string): Promise<TakeoffDocumentResponse[]> => {
    if (!(await isModuleLoaded('oe_takeoff'))) return [];
    const url = projectId
      ? `/v1/takeoff/documents/?project_id=${encodeURIComponent(projectId)}`
      : '/v1/takeoff/documents/';
    const payload = await apiGet<unknown>(url);
    return normalizeListResponse<TakeoffDocumentResponse>(payload, ['documents']);
  },

  /** Delete an uploaded takeoff document. */
  deleteDocument: (docId: string) =>
    apiDelete(`/v1/takeoff/documents/${docId}`),

  /** Compare the measurements of two takeoff documents (revision compare).
   *  ``fromDocumentId`` is the baseline ('before'); ``toDocumentId`` the
   *  target ('after'). Returns added / removed / modified / unchanged rows
   *  plus a money cost impact for linked-to-BOQ measurements that changed. */
  compare: (projectId: string, fromDocumentId: string, toDocumentId: string) =>
    apiPost<TakeoffCompareResponse>(
      `/v1/takeoff/measurements/compare/?project_id=${encodeURIComponent(projectId)}`
        + `&from_document_id=${encodeURIComponent(fromDocumentId)}`
        + `&to_document_id=${encodeURIComponent(toDocumentId)}`,
    ),

  /** Turn a PDF revision-compare delta into a DRAFT variation request.
   *  The backend recomputes the deterministic compare and shapes its net
   *  cost impact into a draft VariationRequest (never submitted - a human
   *  confirms it in the variations module). Requires both ``takeoff.read``
   *  and ``variations.create`` permissions. */
  createVariation: (
    projectId: string,
    fromDocumentId: string,
    toDocumentId: string,
    title?: string,
  ) =>
    apiPost<CreateVariationFromCompareResult>(
      '/v1/takeoff/measurements/create-variation',
      {
        project_id: projectId,
        from_document_id: fromDocumentId,
        to_document_id: toDocumentId,
        ...(title ? { title } : {}),
      },
    ),

  /** Save a CAD takeoff session to a project as a BIM model. */
  saveToProject: (
    sessionId: string,
    projectId: string,
    modelName: string = 'Imported from Takeoff',
  ) =>
    apiPost<{ model_id: string; element_count: number; model_name: string; project_id: string }>(
      `/v1/takeoff/sessions/${sessionId}/save-to-project/?project_id=${encodeURIComponent(projectId)}`,
      { model_name: modelName },
    ),
};
