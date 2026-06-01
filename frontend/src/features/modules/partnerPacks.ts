/**
 * Partner-pack apply / update / un-apply client + React Query hooks.
 *
 * Backend: backend/app/core/partner_pack/router.py
 *   GET  /v1/partner-pack/applied            -> AppliedInfo
 *   GET  /v1/partner-pack/apply-preview/{slug} -> ApplyPreview (dry-run)
 *   POST /v1/partner-pack/apply              { slug, confirm_disables }
 *   POST /v1/partner-pack/unapply
 *   POST /v1/partner-pack/rescan
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost } from '@/shared/lib/api';

export interface AppliedInfo {
  applied: boolean;
  source?: 'in-app' | 'env' | null;
  slug?: string | null;
  pack_version?: string;
  applied_at?: string;
  applied_by?: string | null;
  installed?: boolean;
  available_version?: string | null;
  update_available?: boolean;
}

export interface ApplyPlan {
  branding: {
    partner_name: string;
    powered_by: string;
    primary_color: string;
    accent_color?: string | null;
  };
  modules_to_enable: string[];
  modules_to_enable_missing: string[];
  modules_to_disable: string[];
  modules_to_disable_missing: string[];
  default_currency: string;
  default_locale: string;
  additional_locales: string[];
  rule_packs_active: string[];
  rule_packs_documentation_only: string[];
  cwicr_regions: string[];
  default_tax_template?: string | null;
  demo_project?: PackDemoProject | null;
  warnings: string[];
}

export interface PackDemoProject {
  demo_id: string;
  name?: string;
  currency?: string;
  positions?: number;
  region?: string;
  classification_standard?: string;
}

export interface ApplyPreview {
  slug: string;
  partner_name: string;
  pack_version: string;
  will_disable_modules: boolean;
  will_install_demo: boolean;
  plan: ApplyPlan;
}

export interface ApplyResult {
  applied: boolean;
  slug: string;
  pack_version: string;
  effects: {
    modules_enabled: string[];
    modules_disabled: string[];
    modules_failed: { name: string; action: string; error: string }[];
    demo_project?: {
      demo_id: string;
      project_id?: string;
      project_name?: string;
      already_installed: boolean;
    };
    demo_project_failed?: { error: string };
  };
  skipped_disables: string[];
  warnings: string[];
}

const KEY_APPLIED = 'partner-pack-applied';
const KEY_INSTALLED = 'partner-packs';

export function useAppliedPack() {
  return useQuery({
    queryKey: [KEY_APPLIED],
    queryFn: () => apiGet<AppliedInfo>('/v1/partner-pack/applied'),
    staleTime: 60_000,
  });
}

export function useApplyPreview(slug: string | null) {
  return useQuery({
    queryKey: ['partner-pack-preview', slug],
    queryFn: () =>
      apiGet<ApplyPreview>(`/v1/partner-pack/apply-preview/${encodeURIComponent(slug as string)}`),
    enabled: Boolean(slug),
    staleTime: 30_000,
  });
}

function useInvalidatePackQueries() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: [KEY_INSTALLED] });
    void qc.invalidateQueries({ queryKey: [KEY_APPLIED] });
    // The boot-time co-brand hook (usePartnerPack) keys off this.
    void qc.invalidateQueries({ queryKey: ['partner-pack', 'current'] });
  };
}

export function useApplyPack() {
  const invalidate = useInvalidatePackQueries();
  return useMutation({
    mutationFn: (vars: { slug: string; confirm_disables: boolean; install_demo?: boolean }) =>
      apiPost<ApplyResult>('/v1/partner-pack/apply', vars),
    onSuccess: invalidate,
  });
}

export function useUnapplyPack() {
  const invalidate = useInvalidatePackQueries();
  return useMutation({
    mutationFn: () => apiPost<{ applied: boolean; restored_modules: string[] }>(
      '/v1/partner-pack/unapply',
      {},
    ),
    onSuccess: invalidate,
  });
}

export function useRescanPacks() {
  const invalidate = useInvalidatePackQueries();
  return useMutation({
    mutationFn: () => apiPost<{ count: number; slugs: string[] }>('/v1/partner-pack/rescan', {}),
    onSuccess: invalidate,
  });
}
