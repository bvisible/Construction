/**
 * API helpers for Payroll.
 *
 * All endpoints are prefixed with /v1/payroll/ and are manager-scoped.
 * Money is returned as Decimal-as-string; the UI parses with Number(...)
 * only for display.
 */

import { apiGet, apiPatch, apiPost, getAuthToken } from '@/shared/lib/api';

/* ── Types ─────────────────────────────────────────────────────────────── */

export type PayrollStatus = 'draft' | 'submitted' | 'approved' | 'posted';

export interface PayrollEntry {
  id: string;
  batch_id: string;
  resource_id: string | null;
  worker: string;
  work_date: string | null;
  hours: string;
  rate: string;
  amount: string;
  currency: string;
  source: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface PayrollBatch {
  id: string;
  project_id: string;
  period_label: string;
  period_start: string | null;
  period_end: string | null;
  status: PayrollStatus;
  currency: string;
  total_hours: string;
  total_amount: string;
  entry_count: number;
  notes: string;
  created_by: string | null;
  submitted_at: string | null;
  submitted_by: string | null;
  approved_at: string | null;
  approved_by: string | null;
  posted_at: string | null;
  posted_by: string | null;
  gl_transaction_ref: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ReconciliationRow {
  worker_key: string;
  work_date: string | null;
  resource_id: string | null;
  batch_hours: string;
  source_hours: string;
  delta_hours: string;
  matched: boolean;
}

export interface Reconciliation {
  batch_id: string;
  project_id: string;
  batch_total_hours: string;
  source_total_hours: string;
  delta_total_hours: string;
  balanced: boolean;
  rows: ReconciliationRow[];
}

export interface PayrollBatchDetail extends PayrollBatch {
  entries: PayrollEntry[];
}

export interface LabourCost {
  project_id: string;
  currency: string;
  labour_cost: string;
  total_hours: string;
}

export interface GenerateBatchPayload {
  date_from?: string | null;
  date_to?: string | null;
  period_label?: string | null;
  notes?: string;
}

/* ── API functions ─────────────────────────────────────────────────────── */

export async function fetchPayrollBatches(projectId: string): Promise<PayrollBatch[]> {
  if (!projectId) return [];
  const res = await apiGet<PayrollBatch[]>(
    `/v1/payroll/projects/${encodeURIComponent(projectId)}/batches/`,
  );
  return Array.isArray(res) ? res : [];
}

export async function fetchPayrollBatch(batchId: string): Promise<PayrollBatchDetail> {
  return apiGet<PayrollBatchDetail>(`/v1/payroll/batches/${encodeURIComponent(batchId)}`);
}

export async function generatePayrollBatch(
  projectId: string,
  payload: GenerateBatchPayload,
): Promise<PayrollBatchDetail> {
  return apiPost<PayrollBatchDetail, GenerateBatchPayload>(
    `/v1/payroll/projects/${encodeURIComponent(projectId)}/batches/`,
    payload,
  );
}

export async function fetchLabourCost(projectId: string): Promise<LabourCost | null> {
  if (!projectId) return null;
  return apiGet<LabourCost>(
    `/v1/payroll/projects/${encodeURIComponent(projectId)}/labour-cost/`,
  );
}

/**
 * Finalize (approve) a draft batch: transitions it to `approved` and posts its
 * labour cost to the project budget. Idempotent - calling twice on an
 * already-approved batch returns the unchanged batch.
 */
export async function finalizeBatch(batchId: string): Promise<PayrollBatchDetail> {
  return apiPatch<PayrollBatchDetail>(
    `/v1/payroll/batches/${encodeURIComponent(batchId)}/finalize/`,
  );
}

/** Submit a draft batch for approval (no money moved). Idempotent. */
export async function submitBatch(batchId: string): Promise<PayrollBatchDetail> {
  return apiPatch<PayrollBatchDetail>(
    `/v1/payroll/batches/${encodeURIComponent(batchId)}/submit/`,
  );
}

/** Post an approved batch to the finance ledger (terminal). Idempotent. */
export async function postBatch(batchId: string): Promise<PayrollBatchDetail> {
  return apiPatch<PayrollBatchDetail>(
    `/v1/payroll/batches/${encodeURIComponent(batchId)}/post/`,
  );
}

/** Reconcile a batch's hours against the live field-labour sources (read-only). */
export async function reconcileBatch(batchId: string): Promise<Reconciliation> {
  return apiGet<Reconciliation>(
    `/v1/payroll/batches/${encodeURIComponent(batchId)}/reconcile/`,
  );
}

/**
 * Fetch a batch export (CSV or JSON) with the auth token attached and trigger a
 * browser download. The export endpoints are auth-gated, so a bare anchor href
 * would 401 - we fetch the blob with the Bearer token and save it client-side.
 */
export async function downloadBatchExport(batchId: string, format: 'csv' | 'json'): Promise<void> {
  const token = getAuthToken();
  const res = await fetch(
    `/api/v1/payroll/batches/${encodeURIComponent(batchId)}/export.${format}`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} },
  );
  if (!res.ok) {
    throw new Error(`Export failed (${res.status})`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `payroll-batch-${batchId}.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
