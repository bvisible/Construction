// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// ApprovalInstancesList — running + recent approval workflows, filtered
// by target kind / status. Pure list view; per-instance actions live on
// the consumer page via the ApprovalInstanceCard drop-in.

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { ListChecks, Search } from 'lucide-react';

import { Badge, Card, EmptyState, SkeletonTable } from '@/shared/ui';
import { approvalRoutesKeys, getMeta, listInstances } from './api';
import { kindLabel } from './labels';
import type { ApprovalInstance, InstanceStatus } from './types';

// Mirrors models.INSTANCE_STATUSES — ``pending`` is the active state
// (there is no separate ``in_progress``).
const STATUSES: InstanceStatus[] = [
  'pending',
  'approved',
  'rejected',
  'cancelled',
];

function statusBadge(status: InstanceStatus): {
  variant: 'neutral' | 'blue' | 'success' | 'warning' | 'error';
} {
  return {
    variant:
      status === 'approved'
        ? 'success'
        : status === 'rejected'
          ? 'error'
          : status === 'cancelled'
            ? 'neutral'
            : 'blue',
  };
}

export interface ApprovalInstancesListProps {
  /** Pre-select a target kind filter (no UI control when set). */
  targetKind?: string | null;
  /** Pre-select a project filter. */
  projectId?: string | null;
}

export function ApprovalInstancesList({
  targetKind: pinnedKind,
  projectId,
}: ApprovalInstancesListProps) {
  const { t } = useTranslation();
  const [kindFilter, setKindFilter] = useState<string>(pinnedKind ?? '');
  const [statusFilter, setStatusFilter] = useState<InstanceStatus | ''>('');
  const [search, setSearch] = useState('');

  const effectiveKind = pinnedKind ?? (kindFilter || null);

  // Target kinds come straight from the backend whitelist so the picker
  // can never drift from the validated set.
  const { data: meta } = useQuery({
    queryKey: approvalRoutesKeys.meta(),
    queryFn: () => getMeta(),
    staleTime: 10 * 60_000,
  });
  const targetKinds = meta?.target_kinds ?? [];

  const { data: instances = [], isLoading } = useQuery({
    queryKey: approvalRoutesKeys.instances(
      effectiveKind,
      null,
      projectId,
      statusFilter || null,
    ),
    queryFn: () =>
      listInstances({
        targetKind: effectiveKind,
        projectId,
        status: statusFilter || null,
      }),
    staleTime: 15_000,
  });

  const filtered = instances.filter((i) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      i.target_id.toLowerCase().includes(q) ||
      i.target_kind.toLowerCase().includes(q)
    );
  });

  return (
    <Card padding="none" className="overflow-hidden">
      <div className="flex items-center gap-2 flex-wrap px-3 py-2 border-b border-border-light bg-surface-secondary/40">
        {!pinnedKind && (
          <select
            value={kindFilter}
            onChange={(e) => setKindFilter(e.target.value)}
            className="h-8 rounded-md border border-border bg-surface-primary px-2 text-xs focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue cursor-pointer"
            aria-label={t('approvalRoutes.filter_kind', {
              defaultValue: 'Filter by kind',
            })}
          >
            <option value="">
              {t('approvalRoutes.all_kinds', { defaultValue: 'All target kinds' })}
            </option>
            {targetKinds.map((k) => (
              <option key={k} value={k}>
                {kindLabel(t, k)}
              </option>
            ))}
          </select>
        )}
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as InstanceStatus | '')}
          className="h-8 rounded-md border border-border bg-surface-primary px-2 text-xs focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue cursor-pointer"
          aria-label={t('approvalRoutes.filter_status', {
            defaultValue: 'Filter by status',
          })}
        >
          <option value="">
            {t('approvalRoutes.all_statuses', { defaultValue: 'All statuses' })}
          </option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {t(`approvalRoutes.status_${s}`, {
                defaultValue: s.charAt(0).toUpperCase() + s.slice(1),
              })}
            </option>
          ))}
        </select>
        <div className="relative flex-1 min-w-[180px] max-w-xs ml-auto">
          <Search
            size={13}
            className="absolute left-2.5 top-1/2 -translate-y-1/2 text-content-tertiary"
          />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('common.search', { defaultValue: 'Search…' })}
            aria-label={t('common.search', { defaultValue: 'Search…' })}
            className="h-8 w-full pl-7 rounded-md border border-border bg-surface-primary text-xs focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue"
          />
        </div>
      </div>

      {isLoading ? (
        <div className="p-3">
          <SkeletonTable rows={4} columns={4} />
        </div>
      ) : filtered.length === 0 ? (
        <div className="p-6">
          <EmptyState
            icon={<ListChecks size={28} strokeWidth={1.5} />}
            title={t('approvalRoutes.empty_instances_title', {
              defaultValue: 'No approval workflows',
            })}
            description={t('approvalRoutes.empty_instances_desc', {
              defaultValue:
                'Approval workflows started from any module (markups, submittals, RFIs, …) show up here. Start one from the matching record.',
            })}
          />
        </div>
      ) : (
        <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[640px]">
          <thead>
            <tr className="border-b border-border-light bg-surface-secondary/30">
              <th className="px-3 py-2 text-left text-2xs font-semibold uppercase tracking-wider text-content-tertiary">
                {t('approvalRoutes.col_target', { defaultValue: 'Target' })}
              </th>
              <th className="px-3 py-2 text-left text-2xs font-semibold uppercase tracking-wider text-content-tertiary">
                {t('approvalRoutes.col_status', { defaultValue: 'Status' })}
              </th>
              <th className="px-3 py-2 text-left text-2xs font-semibold uppercase tracking-wider text-content-tertiary">
                {t('approvalRoutes.col_step', { defaultValue: 'Step' })}
              </th>
              <th className="px-3 py-2 text-left text-2xs font-semibold uppercase tracking-wider text-content-tertiary">
                {t('approvalRoutes.col_started', { defaultValue: 'Started' })}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-light">
            {filtered.map((i) => (
              <InstanceRow key={i.id} instance={i} />
            ))}
          </tbody>
        </table>
        </div>
      )}
    </Card>
  );
}

function InstanceRow({ instance }: { instance: ApprovalInstance }) {
  const { t } = useTranslation();
  const { variant } = statusBadge(instance.status);
  return (
    <tr className="hover:bg-surface-secondary/40 transition-colors">
      <td className="px-3 py-2.5 text-xs text-content-secondary">
        <span className="inline-flex items-center gap-1">
          <span>{kindLabel(t, instance.target_kind)}</span>
          <span className="text-content-tertiary tabular-nums">
            {instance.target_id.slice(0, 8)}…
          </span>
        </span>
      </td>
      <td className="px-3 py-2.5">
        <Badge variant={variant} size="sm">
          {t(`approvalRoutes.status_${instance.status}`, {
            defaultValue:
              instance.status.charAt(0).toUpperCase() + instance.status.slice(1),
          })}
        </Badge>
      </td>
      <td className="px-3 py-2.5 text-xs text-content-secondary tabular-nums">
        {instance.status === 'pending'
          ? t('approvalRoutes.step_n', {
              defaultValue: 'Step {{n}}',
              n: instance.current_step_ordinal,
            })
          : '—'}
      </td>
      <td className="px-3 py-2.5 text-xs text-content-tertiary">
        {new Date(instance.started_at).toLocaleDateString()}
      </td>
    </tr>
  );
}
