/**
 * NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OpenConstructionERP.
 *
 * API client for the Swiss CAN / NPK text catalogue: a library of position
 * WORDINGS, where the parent line carries no unit and only its sub-positions
 * are measurable. See backend/app/modules/neoffice/models.py.
 */
import { apiDelete, apiGet, apiPost, apiPut } from '@/shared/lib/api';

export interface TextPosition {
  id: string;
  code: string;
  title: string;
  body: string;
  unit: string | null;
  /** True when the row carries a unit, i.e. it can hold a quantity in a BOQ. */
  measurable: boolean;
  assembly_id: string | null;
  sort_order: number;
  children: TextPosition[];
}

export interface TextCatalogSummary {
  id: string;
  code: string;
  name: string;
  description: string;
  standard: string;
  language: string;
  project_id: string | null;
  position_count: number;
}

export interface TextCatalogTree {
  id: string;
  code: string;
  name: string;
  standard: string;
  positions: TextPosition[];
}

export interface InsertResult {
  boq_position_id: string;
  ordinal: string;
  description: string;
  unit: string | null;
  unit_rate: string;
  assembly_applied: boolean;
  resources_copied: number;
}

const BASE = '/v1/neoffice/text-catalog';

export const textCatalogApi = {
  list: (projectId?: string) =>
    apiGet<TextCatalogSummary[]>(
      `${BASE}/${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''}`,
    ),

  create: (data: {
    code: string;
    name: string;
    description?: string;
    standard?: string;
    language?: string;
    project_id?: string | null;
  }) => apiPost<{ id: string; code: string; name: string }>(`${BASE}/`, data),

  tree: (catalogId: string) =>
    apiGet<TextCatalogTree>(`${BASE}/${encodeURIComponent(catalogId)}/tree/`),

  createPosition: (
    catalogId: string,
    data: {
      code: string;
      title?: string;
      body?: string;
      /** Leave empty for a wording line; set it on a measurable sub-position. */
      unit?: string | null;
      parent_id?: string | null;
      assembly_id?: string | null;
      sort_order?: number;
    },
  ) => apiPost<TextPosition>(`${BASE}/${encodeURIComponent(catalogId)}/positions/`, data),

  updatePosition: (
    positionId: string,
    data: Partial<{
      code: string;
      title: string;
      body: string;
      unit: string | null;
      assembly_id: string | null;
      sort_order: number;
    }>,
  ) => apiPut<TextPosition>(`${BASE}/positions/${encodeURIComponent(positionId)}/`, data),

  deletePosition: (positionId: string) =>
    apiDelete(`${BASE}/positions/${encodeURIComponent(positionId)}/`),

  /** Create a BOQ position from this wording, bringing its assembly along. */
  insertIntoBoq: (
    positionId: string,
    data: { boq_id: string; parent_id?: string | null; ordinal?: string; quantity?: string },
  ) =>
    apiPost<InsertResult>(
      `${BASE}/positions/${encodeURIComponent(positionId)}/insert-into-boq/`,
      data,
    ),
};
