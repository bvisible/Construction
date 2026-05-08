/**
 * NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OCE.
 *
 * Type definitions for the Swiss Pack API responses.
 */

export interface Translation {
  fr?: string | null;
  de?: string | null;
  it?: string | null;
  en?: string | null;
}

export interface StandardSummary {
  code: string;
  name: string;
  description: string;
  size: number;
}

export interface ClassificationEntry {
  code: string;
  parent_code?: string | null;
  level: number;
  label: Translation;
  is_sipal_specific?: boolean;
  chapter_edition_year?: number | null;
  chapter_edition_lang?: 'F' | 'D' | 'I' | null;
}

export interface ServicePhase {
  phase: string;
  title: string;
  subphase?: string;
  fee_share_pct?: string;
}

export interface StandardDetail {
  code: string;
  name: string;
  description: string;
  sia_reference?: string | null;
  publisher?: string;
  language?: string;
  entries?: ClassificationEntry[];
  service_phases?: ServicePhase[];
  warranty_years?: number;
  defect_liability_years?: number;
  note?: string;
  use_case?: string;
}

export interface TaxRule {
  code: string;
  name: string;
  name_i18n?: Record<string, string>;
  type: string;
  country: string;
  rate_pct: string;
  effective_from?: string;
  use_case?: string;
}

export interface ContractType {
  code: string;
  name: string;
  name_i18n?: Record<string, string>;
  description: string;
  sia_reference?: string;
}

export interface ClassificationSummary {
  CFC?: ClassificationSummaryEntry[];
  'eBKP-H'?: ClassificationSummaryEntry[];
  'eBKP-T'?: ClassificationSummaryEntry[];
  NPK?: ClassificationSummaryEntry[];
}

export interface ClassificationSummaryEntry {
  code: string;
  label_fr: string | null;
  level: number;
  is_sipal_specific?: boolean;
}
