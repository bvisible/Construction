/**
 * API helpers for Correspondence Log.
 *
 * All endpoints are prefixed with /v1/correspondence/.
 */

import { apiDelete, apiGet, apiPatch, apiPost } from '@/shared/lib/api';

/* ── Types ─────────────────────────────────────────────────────────────── */

export type CorrespondenceDirection = 'incoming' | 'outgoing';

export type CorrespondenceType = 'letter' | 'email' | 'notice' | 'memo';

export interface Correspondence {
  id: string;
  project_id: string;
  reference_number: string;
  subject: string;
  direction: CorrespondenceDirection;
  correspondence_type: CorrespondenceType;
  from_contact_id: string | null;
  to_contact_ids: string[];
  date_sent: string | null;
  date_received: string | null;
  /** Document UUIDs from the Documents module referenced by this entry. */
  linked_document_ids: string[];
  /** Optional link back to the Transmittal this letter relates to. */
  linked_transmittal_id: string | null;
  /** Optional link back to the RFI this letter relates to. */
  linked_rfi_id: string | null;
  notes: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface CorrespondenceFilters {
  project_id?: string;
  direction?: CorrespondenceDirection | '';
  type?: CorrespondenceType | '';
}

export interface CreateCorrespondencePayload {
  project_id: string;
  subject: string;
  direction: CorrespondenceDirection;
  correspondence_type: CorrespondenceType;
  from_contact_id?: string;
  to_contact_ids?: string[];
  date_sent?: string;
  date_received?: string;
  notes?: string;
}

export interface UpdateCorrespondencePayload {
  subject?: string;
  direction?: CorrespondenceDirection;
  correspondence_type?: CorrespondenceType;
  from_contact_id?: string;
  to_contact_ids?: string[];
  date_sent?: string;
  date_received?: string;
  notes?: string | null;
}

/**
 * The API may not always return the newer link arrays on every record
 * (older rows / partial serialisers). Normalise so the UI never has to
 * guard `undefined` on `.length`.
 */
type CorrespondenceWire = Omit<
  Correspondence,
  'to_contact_ids' | 'linked_document_ids' | 'linked_transmittal_id' | 'linked_rfi_id'
> & {
  to_contact_ids?: string[] | null;
  linked_document_ids?: string[] | null;
  linked_transmittal_id?: string | null;
  linked_rfi_id?: string | null;
};

function normaliseCorrespondence(c: CorrespondenceWire): Correspondence {
  return {
    ...c,
    to_contact_ids: c.to_contact_ids ?? [],
    linked_document_ids: c.linked_document_ids ?? [],
    linked_transmittal_id: c.linked_transmittal_id ?? null,
    linked_rfi_id: c.linked_rfi_id ?? null,
  } as Correspondence;
}

/* ── API Functions ─────────────────────────────────────────────────────── */

export async function fetchCorrespondence(
  filters?: CorrespondenceFilters,
): Promise<Correspondence[]> {
  const params = new URLSearchParams();
  if (filters?.project_id) params.set('project_id', filters.project_id);
  if (filters?.direction) params.set('direction', filters.direction);
  if (filters?.type) params.set('type', filters.type);
  const qs = params.toString();
  const rows = await apiGet<CorrespondenceWire[]>(
    `/v1/correspondence/${qs ? `?${qs}` : ''}`,
  );
  return rows.map(normaliseCorrespondence);
}

export async function createCorrespondence(
  data: CreateCorrespondencePayload,
): Promise<Correspondence> {
  const row = await apiPost<CorrespondenceWire>('/v1/correspondence/', data);
  return normaliseCorrespondence(row);
}

export async function updateCorrespondence(
  id: string,
  data: UpdateCorrespondencePayload,
): Promise<Correspondence> {
  const row = await apiPatch<CorrespondenceWire>(`/v1/correspondence/${id}`, data);
  return normaliseCorrespondence(row);
}

export async function deleteCorrespondence(id: string): Promise<void> {
  await apiDelete(`/v1/correspondence/${id}`);
}
