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
  // //// NEOFFICE PATCH — a wording insert also brings its measurable
  // sub-positions; the caller needs to say so. //// END NEOFFICE PATCH
  is_wording?: boolean;
  children_inserted?: number;
  //// NEOFFICE PATCH — how many rows received a price analysis. A wording has
  //// none of its own; its sub-positions do, so a per-row count is the only
  //// honest number. //// END NEOFFICE PATCH
  assemblies_applied?: number;
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

  //// NEOFFICE PATCH — insert an explicit selection. No quantity: the
  //// estimator types it in the grid, where the other quantities are.
  insertManyIntoBoq: (data: {
    boq_id: string;
    parent_id?: string | null;
    position_ids: string[];
    with_assembly?: boolean;
  }) =>
    apiPost<{ inserted: number; assemblies_applied: number; codes: string[] }>(
      `${BASE}/insert-many-into-boq/`,
      data,
    ),
  //// END NEOFFICE PATCH

  //// NEOFFICE PATCH — which catalogue texts depend on this assembly. Editing
  //// an assembly used to be editing something whose blast radius was
  //// invisible. //// END NEOFFICE PATCH
  usedByAssembly: (assemblyId: string) =>
    apiGet<
      Array<{
        id: string;
        code: string;
        title: string;
        unit: string | null;
        catalog_id: string;
        catalog_code: string;
        catalog_name: string;
      }>
    >(`${BASE}/by-assembly/${encodeURIComponent(assemblyId)}/`),

  /** Create a BOQ position from this wording, bringing its assembly along. */
  insertIntoBoq: (
    positionId: string,
    data: {
      boq_id: string;
      parent_id?: string | null;
      ordinal?: string;
      quantity?: string;
      //// NEOFFICE PATCH — false inserts the text without its price analysis.
      with_assembly?: boolean;
      //// END NEOFFICE PATCH
    },
  ) =>
    apiPost<InsertResult>(
      `${BASE}/positions/${encodeURIComponent(positionId)}/insert-into-boq/`,
      data,
    ),
};
