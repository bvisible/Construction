import { apiDelete, apiGet, apiPatch, apiPost } from '@/shared/lib/api';

// ── Types ────────────────────────────────────────────────────────────────────

export type ComponentType =
  | 'labor'
  | 'fg_admin'
  | 'machine'
  | 'material'
  | 'internal_loc'
  | 'external_loc'
  | 'external_margin'
  | 'subcontractor'
  | 'subcontractor_margin'
  | 'misc'
  | 'transport';

export const COMPONENT_TYPES: ComponentType[] = [
  'labor',
  'fg_admin',
  'machine',
  'material',
  'internal_loc',
  'external_loc',
  'external_margin',
  'subcontractor',
  'subcontractor_margin',
  'misc',
  'transport',
];

export interface AssemblyComponent {
  id: string;
  cost_line_id: string;
  sub_block_label: string;
  component_type: ComponentType;
  description: string;
  unit: string | null;
  unit_rate: string;
  discount: string | null;
  qty: string | null;
  yield_per_hour: string | null;
  amount: string;
  sort_order: number;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AssemblyComponentCreate {
  sub_block_label?: string;
  component_type: ComponentType;
  description?: string;
  unit?: string | null;
  unit_rate?: string;
  discount?: string | null;
  qty?: string | null;
  yield_per_hour?: string | null;
  amount?: string;
  sort_order?: number;
  metadata?: Record<string, unknown>;
}

export interface AssemblyComponentUpdate {
  sub_block_label?: string;
  component_type?: ComponentType;
  description?: string;
  unit?: string | null;
  unit_rate?: string;
  discount?: string | null;
  qty?: string | null;
  yield_per_hour?: string | null;
  amount?: string;
  sort_order?: number;
  metadata?: Record<string, unknown>;
}

export interface RecomputeResult {
  cost_line_id: string;
  project_id: string;
  components_count: number;
  components_total: string;
}

export type YieldSource = 'import' | 'calibrated' | 'manual';

export interface YieldLibraryEntry {
  id: string;
  project_id: string | null;
  task_label: string;
  unit: string;
  yield_per_hour: string;
  source: YieldSource;
  source_ref: string | null;
  last_calibrated_at: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface YieldLibraryEntryCreate {
  project_id?: string | null;
  task_label: string;
  unit?: string;
  yield_per_hour?: string;
  source?: YieldSource;
  source_ref?: string | null;
  metadata?: Record<string, unknown>;
}

export interface YieldLibraryEntryUpdate {
  task_label?: string;
  unit?: string;
  yield_per_hour?: string;
  source?: YieldSource;
  source_ref?: string | null;
  metadata?: Record<string, unknown>;
}

// ── Endpoints ────────────────────────────────────────────────────────────────

const BASE = '/v1/costmodel_typed';

export const costModelTypedApi = {
  // ── Assembly components ──────────────────────────────────────────────────
  listComponentsForCostLine: (costLineId: string) =>
    apiGet<AssemblyComponent[]>(`${BASE}/spine/lines/${costLineId}/components`),
  createComponent: (costLineId: string, body: AssemblyComponentCreate) =>
    apiPost<AssemblyComponent, AssemblyComponentCreate>(
      `${BASE}/spine/lines/${costLineId}/components`,
      body,
    ),
  recomputeCostLine: (costLineId: string) =>
    apiPost<RecomputeResult, Record<string, never>>(
      `${BASE}/spine/lines/${costLineId}/recompute`,
      {} as Record<string, never>,
    ),
  updateComponent: (componentId: string, body: AssemblyComponentUpdate) =>
    apiPatch<AssemblyComponent, AssemblyComponentUpdate>(
      `${BASE}/typed/components/${componentId}`,
      body,
    ),
  deleteComponent: (componentId: string) =>
    apiDelete(`${BASE}/typed/components/${componentId}`),
  listComponentsForProject: (
    projectId: string,
    params: { component_type?: ComponentType; offset?: number; limit?: number } = {},
  ) => {
    const q = new URLSearchParams();
    if (params.component_type) q.set('component_type', params.component_type);
    if (params.offset != null) q.set('offset', String(params.offset));
    if (params.limit != null) q.set('limit', String(params.limit));
    const qs = q.toString();
    return apiGet<AssemblyComponent[]>(
      `${BASE}/projects/${projectId}/typed/components${qs ? `?${qs}` : ''}`,
    );
  },

  // ── Yield library ────────────────────────────────────────────────────────
  listYieldEntries: (
    params: {
      project_id?: string | null;
      include_global?: boolean;
      offset?: number;
      limit?: number;
    } = {},
  ) => {
    const q = new URLSearchParams();
    if (params.project_id != null) q.set('project_id', params.project_id);
    if (params.include_global != null) q.set('include_global', String(params.include_global));
    if (params.offset != null) q.set('offset', String(params.offset));
    if (params.limit != null) q.set('limit', String(params.limit));
    const qs = q.toString();
    return apiGet<YieldLibraryEntry[]>(`${BASE}/yield-library${qs ? `?${qs}` : ''}`);
  },
  searchYieldEntries: (q: string, limit = 50) => {
    const params = new URLSearchParams({ q, limit: String(limit) });
    return apiGet<YieldLibraryEntry[]>(`${BASE}/yield-library/search?${params.toString()}`);
  },
  createYieldEntry: (body: YieldLibraryEntryCreate) =>
    apiPost<YieldLibraryEntry, YieldLibraryEntryCreate>(`${BASE}/yield-library`, body),
  updateYieldEntry: (entryId: string, body: YieldLibraryEntryUpdate) =>
    apiPatch<YieldLibraryEntry, YieldLibraryEntryUpdate>(
      `${BASE}/yield-library/${entryId}`,
      body,
    ),
  deleteYieldEntry: (entryId: string) => apiDelete(`${BASE}/yield-library/${entryId}`),
};
