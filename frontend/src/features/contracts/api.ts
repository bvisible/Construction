/**
 * API helpers for the Contracts module (type-rich construction contracts).
 *
 * Backed by /api/v1/contracts/ — see backend/app/modules/contracts/router.py
 * and schemas.py. The shapes here mirror the Pydantic response models
 * exactly so the page can drop into the API once it's mounted.
 *
 * Backwards-compat: the older `Contract` / `ProgressClaim` / `FinalAccount`
 * names from the previous skeleton are re-exported under their original
 * aliases at the bottom so any in-flight call sites still type-check.
 */

import { apiGet, apiPost, apiPatch, apiDelete } from '@/shared/lib/api';

/* ── Enums / unions ───────────────────────────────────────────────────── */

export type ContractType =
  | 'lump_sum'
  | 'gmp'
  | 'cost_plus'
  | 'tm'
  | 'unit_price'
  | 'design_build'
  | 'combination';

export type CounterpartyType = 'client' | 'subcontractor';

export type ContractStatus =
  | 'draft'
  | 'active'
  | 'suspended'
  | 'completed'
  | 'terminated';

export type RetentionReleaseEvent =
  | 'practical_completion'
  | 'final_account'
  | 'handover';

export type ContractLineType =
  | 'work'
  | 'material'
  | 'labor'
  | 'fee'
  | 'contingency'
  | 'allowance';

export type ClaimStatus =
  | 'draft'
  | 'submitted'
  | 'approved'
  | 'certified'
  | 'paid'
  | 'rejected';

export type FinalAccountStatus = 'draft' | 'agreed' | 'disputed' | 'closed';

export type FeeType = 'percent_of_cost' | 'fixed' | 'sliding_scale';

export type OverrunResponsibility = 'contractor' | 'shared' | 'owner';

/* ── Domain models ────────────────────────────────────────────────────── */

export interface ContractItem {
  id: string;
  code: string;
  title: string;
  contract_type: ContractType;
  counterparty_type: CounterpartyType;
  counterparty_id: string | null;
  project_id: string;
  parent_contract_id: string | null;
  start_date: string | null;
  end_date: string | null;
  total_value: number | string;
  currency: string;
  retention_percent: number | string;
  retention_release_event: RetentionReleaseEvent;
  status: ContractStatus;
  signed_at: string | null;
  terms: Record<string, unknown>;
  created_by: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ContractLine {
  id: string;
  contract_id: string;
  parent_line_id: string | null;
  code: string;
  description: string;
  scope_section: string | null;
  line_type: ContractLineType;
  unit: string | null;
  quantity: number | string;
  unit_rate: number | string;
  total_value: number | string;
  order_index: number;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ProgressClaimItem {
  id: string;
  contract_id: string;
  claim_number: string;
  period_start: string | null;
  period_end: string | null;
  claim_date: string | null;
  gross_amount: number | string;
  retention_amount: number | string;
  prior_claims_total: number | string;
  net_due: number | string;
  status: ClaimStatus;
  submitted_at: string | null;
  approved_at: string | null;
  paid_at: string | null;
  currency: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ProgressClaimLine {
  id: string;
  progress_claim_id: string;
  contract_line_id: string;
  period_completed_qty: number | string;
  period_completed_value: number | string;
  period_completed_pct: number | string;
  cumulative_completed_value: number | string;
  created_at: string;
  updated_at: string;
}

export interface FinalAccountItem {
  id: string;
  contract_id: string;
  final_contract_value: number | string;
  total_paid: number | string;
  retention_held: number | string;
  retention_released: number | string;
  final_balance: number | string;
  sign_off_date: string | null;
  sign_off_by: string | null;
  status: FinalAccountStatus;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface RetentionScheduleItem {
  id: string;
  contract_id: string;
  accrual_rule: Record<string, unknown>;
  release_rule: Record<string, unknown>;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface FeeStructureItem {
  id: string;
  contract_id: string;
  fee_type: FeeType;
  fee_percent: number | string;
  fee_fixed_amount: number | string | null;
  sliding_scale: Record<string, unknown>[];
  max_fee: number | string | null;
  created_at: string;
  updated_at: string;
}

export interface GainshareConfigurationItem {
  id: string;
  contract_id: string;
  target_cost: number | string;
  gmp_cap: number | string;
  savings_split_owner_pct: number | string;
  savings_split_contractor_pct: number | string;
  overrun_responsibility: OverrunResponsibility;
  created_at: string;
  updated_at: string;
}

export interface LDClauseItem {
  id: string;
  contract_id: string;
  per_day_amount: number | string;
  currency: string;
  max_amount: number | string | null;
  milestone_id: string | null;
  enforcement_status: 'active' | 'waived';
  created_at: string;
  updated_at: string;
}

export interface ContractDashboard {
  contract_id: string;
  total_value: number | string;
  paid_to_date: number | string;
  retention_held: number | string;
  outstanding: number | string;
  claims_count: number;
  change_orders_count: number;
  gainshare_estimate: number | string | null;
  status: ContractStatus;
}

export interface ContractTypeConfiguration {
  id: string;
  contract_type: ContractType;
  display_name: string;
  allowed_fields: string[];
  default_fee_structure: Record<string, unknown>;
  schema_version: string;
}

/* ── Payloads ─────────────────────────────────────────────────────────── */

export interface ContractCreatePayload {
  code: string;
  title?: string;
  contract_type: ContractType;
  counterparty_type?: CounterpartyType;
  counterparty_id?: string | null;
  project_id: string;
  parent_contract_id?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  total_value?: number;
  currency?: string;
  retention_percent?: number;
  retention_release_event?: RetentionReleaseEvent;
  status?: ContractStatus;
  signed_at?: string | null;
  terms?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

export type ContractUpdatePayload = Partial<Omit<ContractCreatePayload, 'project_id'>>;

export interface ContractLineCreatePayload {
  contract_id: string;
  parent_line_id?: string | null;
  code?: string;
  description?: string;
  scope_section?: string | null;
  line_type?: ContractLineType;
  unit?: string | null;
  quantity?: number;
  unit_rate?: number;
  order_index?: number;
  metadata?: Record<string, unknown>;
}

export interface ProgressClaimCreatePayload {
  contract_id: string;
  claim_number?: string | null;
  period_start?: string | null;
  period_end?: string | null;
  claim_date?: string | null;
  currency?: string;
  metadata?: Record<string, unknown>;
}

export interface FinalAccountCreatePayload {
  contract_id: string;
  final_contract_value?: number;
  total_paid?: number;
  retention_held?: number;
  retention_released?: number;
  final_balance?: number;
  sign_off_date?: string | null;
  sign_off_by?: string | null;
  status?: FinalAccountStatus;
  notes?: string | null;
}

/* ── List filters ─────────────────────────────────────────────────────── */

export interface ContractFilters {
  project_id: string;
  status?: ContractStatus | '';
  contract_type?: ContractType | '';
  counterparty_type?: CounterpartyType | '';
  offset?: number;
  limit?: number;
}

/* ── Internal helpers ─────────────────────────────────────────────────── */

function normaliseList<T>(res: T[] | { items: T[] } | null | undefined): T[] {
  if (!res) return [];
  if (Array.isArray(res)) return res;
  return res.items ?? [];
}

async function safeGetList<T>(path: string): Promise<T[]> {
  try {
    const res = await apiGet<T[] | { items: T[] }>(path);
    return normaliseList(res);
  } catch (err: unknown) {
    if (err && typeof err === 'object' && 'status' in err) {
      const status = (err as { status: number }).status;
      if (status === 404 || status === 501) return [];
    }
    throw err;
  }
}

/* ── Contracts ────────────────────────────────────────────────────────── */

export function listContracts(filters: ContractFilters): Promise<ContractItem[]> {
  const qs = new URLSearchParams();
  qs.set('project_id', filters.project_id);
  if (filters.status) qs.set('status', filters.status);
  if (filters.contract_type) qs.set('contract_type', filters.contract_type);
  if (filters.counterparty_type) qs.set('counterparty_type', filters.counterparty_type);
  if (filters.offset !== undefined) qs.set('offset', String(filters.offset));
  if (filters.limit !== undefined) qs.set('limit', String(filters.limit));
  return safeGetList<ContractItem>(`/v1/contracts/contracts/?${qs.toString()}`);
}

export function getContract(id: string): Promise<ContractItem> {
  return apiGet<ContractItem>(`/v1/contracts/contracts/${id}`);
}

export function createContract(data: ContractCreatePayload): Promise<ContractItem> {
  return apiPost<ContractItem>('/v1/contracts/contracts/', data);
}

export function updateContract(
  id: string,
  data: ContractUpdatePayload,
): Promise<ContractItem> {
  return apiPatch<ContractItem>(`/v1/contracts/contracts/${id}`, data);
}

export function deleteContract(id: string): Promise<void> {
  return apiDelete(`/v1/contracts/contracts/${id}`);
}

export function signContract(id: string): Promise<ContractItem> {
  return apiPost<ContractItem>(`/v1/contracts/contracts/${id}/sign`, {});
}

export function suspendContract(id: string): Promise<ContractItem> {
  return apiPost<ContractItem>(`/v1/contracts/contracts/${id}/suspend`, {});
}

export function resumeContract(id: string): Promise<ContractItem> {
  return apiPost<ContractItem>(`/v1/contracts/contracts/${id}/resume`, {});
}

export function terminateContract(id: string): Promise<ContractItem> {
  return apiPost<ContractItem>(`/v1/contracts/contracts/${id}/terminate`, {});
}

export function getContractDashboard(id: string): Promise<ContractDashboard> {
  return apiGet<ContractDashboard>(`/v1/contracts/contracts/${id}/dashboard`);
}

/* ── Contract lines (SoV) ─────────────────────────────────────────────── */

export function listContractLines(contractId: string): Promise<ContractLine[]> {
  return safeGetList<ContractLine>(`/v1/contracts/contracts/${contractId}/lines`);
}

export function createContractLine(
  contractId: string,
  data: ContractLineCreatePayload,
): Promise<ContractLine> {
  return apiPost<ContractLine>(`/v1/contracts/contracts/${contractId}/lines`, data);
}

/* ── Progress claims ──────────────────────────────────────────────────── */

export function listProgressClaims(params: {
  contract_id: string;
  status?: ClaimStatus | '';
  offset?: number;
  limit?: number;
}): Promise<ProgressClaimItem[]> {
  const qs = new URLSearchParams();
  qs.set('contract_id', params.contract_id);
  if (params.status) qs.set('status', params.status);
  if (params.offset !== undefined) qs.set('offset', String(params.offset));
  if (params.limit !== undefined) qs.set('limit', String(params.limit));
  return safeGetList<ProgressClaimItem>(`/v1/contracts/progress-claims/?${qs.toString()}`);
}

export function getProgressClaim(id: string): Promise<ProgressClaimItem> {
  return apiGet<ProgressClaimItem>(`/v1/contracts/progress-claims/${id}`);
}

export function createProgressClaim(
  data: ProgressClaimCreatePayload,
): Promise<ProgressClaimItem> {
  return apiPost<ProgressClaimItem>('/v1/contracts/progress-claims/', data);
}

export function submitClaim(id: string): Promise<ProgressClaimItem> {
  return apiPost<ProgressClaimItem>(`/v1/contracts/progress-claims/${id}/submit`, {});
}

export function approveClaim(id: string): Promise<ProgressClaimItem> {
  return apiPost<ProgressClaimItem>(`/v1/contracts/progress-claims/${id}/approve`, {});
}

export function certifyClaim(id: string): Promise<ProgressClaimItem> {
  return apiPost<ProgressClaimItem>(`/v1/contracts/progress-claims/${id}/certify`, {});
}

export function rejectClaim(id: string): Promise<ProgressClaimItem> {
  return apiPost<ProgressClaimItem>(`/v1/contracts/progress-claims/${id}/reject`, {});
}

export function markClaimPaid(id: string): Promise<ProgressClaimItem> {
  return apiPost<ProgressClaimItem>(`/v1/contracts/progress-claims/${id}/mark-paid`, {});
}

export function listClaimLines(claimId: string): Promise<ProgressClaimLine[]> {
  return safeGetList<ProgressClaimLine>(`/v1/contracts/progress-claims/${claimId}/lines`);
}

/* ── Retention schedule ───────────────────────────────────────────────── */

export function getRetentionSchedule(scheduleId: string): Promise<RetentionScheduleItem> {
  return apiGet<RetentionScheduleItem>(
    `/v1/contracts/retention-schedules/${scheduleId}`,
  );
}

/* ── Fee structure ────────────────────────────────────────────────────── */

export function getFeeStructure(feeId: string): Promise<FeeStructureItem> {
  return apiGet<FeeStructureItem>(`/v1/contracts/fee-structures/${feeId}`);
}

/* ── Gainshare ────────────────────────────────────────────────────────── */

export function getGainshareConfig(configId: string): Promise<GainshareConfigurationItem> {
  return apiGet<GainshareConfigurationItem>(
    `/v1/contracts/gainshare-configurations/${configId}`,
  );
}

/* ── LD clauses ───────────────────────────────────────────────────────── */

export function getLDClause(ldId: string): Promise<LDClauseItem> {
  return apiGet<LDClauseItem>(`/v1/contracts/ld-clauses/${ldId}`);
}

/* ── Final accounts ───────────────────────────────────────────────────── */

export function getFinalAccount(accountId: string): Promise<FinalAccountItem> {
  return apiGet<FinalAccountItem>(`/v1/contracts/final-accounts/${accountId}`);
}

export function createFinalAccount(
  data: FinalAccountCreatePayload,
): Promise<FinalAccountItem> {
  return apiPost<FinalAccountItem>('/v1/contracts/final-accounts/', data);
}

export function closeContract(
  contractId: string,
  data: FinalAccountCreatePayload,
): Promise<FinalAccountItem> {
  return apiPost<FinalAccountItem>(
    `/v1/contracts/contracts/${contractId}/close`,
    { ...data, contract_id: contractId },
  );
}

/* ── Type configurations ──────────────────────────────────────────────── */

export function listTypeConfigurations(): Promise<ContractTypeConfiguration[]> {
  return safeGetList<ContractTypeConfiguration>('/v1/contracts/type-configurations/');
}

/* ── Clone (deep-copy a contract into draft) ──────────────────────────── */

export interface ContractClonePayload {
  new_code: string;
  new_title?: string | null;
  target_project_id?: string | null;
  include_lines?: boolean;
  copy_subconfigs?: boolean;
}

export function cloneContract(
  contractId: string,
  data: ContractClonePayload,
): Promise<ContractItem> {
  return apiPost<ContractItem>(
    `/v1/contracts/contracts/${contractId}/clone`,
    data,
  );
}

/* ── Clause templates (FIDIC / JCT / NEC / AIA / ConsensusDocs) ───────── */

export interface ClauseTemplate {
  code: string;
  name: string;
  family: string;
  retention_release_event: string;
  clause_count: number;
}

export function listClauseTemplates(): Promise<ClauseTemplate[]> {
  return safeGetList<ClauseTemplate>('/v1/contracts/contract-templates/');
}

/* ── Back-compat aliases (old skeleton names) ─────────────────────────── */

export type Contract = ContractItem;
export type ProgressClaim = ProgressClaimItem;
export type FinalAccount = FinalAccountItem;
export type SoVLine = ContractLine;
