/**
 * InboxPanel - the unified approvals/alerts list.
 *
 * Renders the caller's pending approvals + unread alerts (aggregated by
 * ``GET /api/v1/dashboard/inbox/``) as one chronologically-sorted, clickable
 * list. Reused in two places:
 *   - as a dashboard widget (``compact``, small ``limit``), and
 *   - as the body of the full ``/inbox`` page (``limit`` larger, header off
 *     because the page supplies its own).
 *
 * Each row links to the originating item via its ``action_url``; an alert
 * carries an i18n ``title_key`` we render with its ``body_context``.
 */
import { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  ArrowRight,
  Bell,
  CheckSquare,
  ClipboardCheck,
  Info,
  Inbox as InboxIcon,
  Loader2,
  XCircle,
} from 'lucide-react';
import clsx from 'clsx';
import { Badge, Card, CardContent, CardHeader } from '@/shared/ui';
import { fetchInbox, type InboxItem, type InboxSeverity } from './api';
import {
  countApprovals,
  formatTimeAgo,
  normalizeSeverity,
  resolveTitle,
  sortInboxItems,
} from './inboxUtils';

export interface InboxPanelProps {
  /** Max rows requested from the backend. Default 8 (a compact widget). */
  limit?: number;
  /** Render the card chrome + header. Default true. Pages pass false. */
  showHeader?: boolean;
  /** Tighten spacing for the dashboard widget. */
  compact?: boolean;
}

const SEVERITY_STYLE: Record<
  InboxSeverity,
  { color: string; bg: string }
> = {
  critical: { color: 'text-semantic-error', bg: 'bg-rose-50 dark:bg-rose-900/30' },
  warning: { color: 'text-amber-500', bg: 'bg-amber-50 dark:bg-amber-900/30' },
  info: { color: 'text-oe-blue', bg: 'bg-oe-blue-subtle' },
};

function severityIcon(severity: InboxSeverity) {
  if (severity === 'critical') return XCircle;
  if (severity === 'warning') return AlertTriangle;
  return Info;
}

function kindIcon(item: InboxItem) {
  if (item.kind === 'approval') {
    return item.source === 'change_order' ? ClipboardCheck : CheckSquare;
  }
  return Bell;
}

function InboxRow({ item }: { item: InboxItem }) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const sev = normalizeSeverity(item.severity);
  const sevStyle = SEVERITY_STYLE[sev];
  const KindIcon = kindIcon(item);
  const SevIcon = severityIcon(sev);

  const ctx = useMemo(
    () =>
      item.body_context && typeof item.body_context === 'object'
        ? (item.body_context as Record<string, unknown>)
        : {},
    [item.body_context],
  );

  const titleSpec = resolveTitle(item);
  const title = t(titleSpec.key, { defaultValue: titleSpec.defaultValue, ...ctx });
  const timeAgo = formatTimeAgo(item.created_at, t);

  const onClick = useCallback(() => {
    if (item.action_url) navigate(item.action_url);
  }, [item.action_url, navigate]);

  const clickable = Boolean(item.action_url);
  const RowTag = clickable ? 'button' : 'div';

  return (
    <RowTag
      type={clickable ? 'button' : undefined}
      onClick={clickable ? onClick : undefined}
      className={clsx(
        'group flex w-full items-start gap-3 px-4 py-2.5 text-left',
        'border-b border-border-light/60 last:border-b-0 transition-colors',
        clickable &&
          'hover:bg-surface-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue/40',
      )}
    >
      <span
        className={clsx(
          'shrink-0 h-7 w-7 rounded-md flex items-center justify-center',
          sevStyle.bg,
        )}
      >
        <KindIcon size={14} className={sevStyle.color} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <p className="text-xs font-semibold text-content-primary line-clamp-1">{title}</p>
          {item.kind === 'approval' && (
            <Badge variant="warning" size="sm">
              {t('inbox.badge_approval', { defaultValue: 'Approval' })}
            </Badge>
          )}
        </div>
        <div className="mt-0.5 flex items-center gap-2 text-2xs text-content-tertiary">
          {item.project_name && (
            <span className="truncate max-w-[160px]">{item.project_name}</span>
          )}
          {item.project_name && timeAgo && <span aria-hidden>·</span>}
          {timeAgo && <span className="tabular-nums shrink-0">{timeAgo}</span>}
        </div>
      </div>
      <SevIcon size={13} className={clsx('shrink-0 mt-0.5', sevStyle.color)} aria-hidden />
      {clickable && (
        <ArrowRight
          size={14}
          className="shrink-0 mt-0.5 text-content-quaternary group-hover:text-oe-blue group-hover:translate-x-0.5 transition-all"
        />
      )}
    </RowTag>
  );
}

export function InboxPanel({ limit = 8, showHeader = true, compact = false }: InboxPanelProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['inbox', limit],
    queryFn: () => fetchInbox(limit),
    retry: false,
    staleTime: 30_000,
    refetchOnWindowFocus: true,
  });

  // Defensive client-side re-sort (backend already sorts) + approval count.
  const items = useMemo(() => sortInboxItems(data?.items ?? []), [data?.items]);
  const approvalsCount = data?.approvals_count ?? countApprovals(items);
  const alertsCount = data?.alerts_count ?? items.length - approvalsCount;
  const total = data?.total ?? items.length;

  const body = (
    <>
      {isLoading ? (
        <div className="px-4 py-6 space-y-3" aria-busy="true">
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex items-start gap-2.5">
              <div className="h-7 w-7 rounded-md bg-surface-secondary animate-pulse shrink-0" />
              <div className="flex-1 space-y-1.5">
                <div className="h-2.5 w-3/4 rounded bg-surface-secondary animate-pulse" />
                <div className="h-2 w-1/2 rounded bg-surface-secondary animate-pulse" />
              </div>
            </div>
          ))}
        </div>
      ) : isError ? (
        <div className="px-4 py-6 text-center">
          <XCircle size={20} className="mx-auto mb-2 text-semantic-error" />
          <p className="text-xs text-content-secondary mb-2">
            {t('inbox.load_error', { defaultValue: "Couldn't load your inbox" })}
          </p>
          <button
            onClick={() => refetch()}
            className="text-2xs font-medium text-oe-blue hover:underline inline-flex items-center gap-1"
          >
            <Loader2 size={10} className="hidden" />
            {t('common.retry', { defaultValue: 'Try again' })}
          </button>
        </div>
      ) : items.length === 0 ? (
        <div className="px-4 py-8 text-center">
          <CheckSquare size={24} className="mx-auto mb-2 text-content-quaternary" />
          <p className="text-xs font-medium text-content-secondary">
            {t('inbox.empty_title', { defaultValue: "You're all caught up" })}
          </p>
          <p className="text-2xs text-content-tertiary mt-0.5">
            {t('inbox.empty_desc', {
              defaultValue: 'Pending approvals and alerts will appear here.',
            })}
          </p>
        </div>
      ) : (
        <div className={clsx('overflow-y-auto', compact ? 'max-h-[360px]' : 'max-h-[640px]')}>
          {items.map((item) => (
            <InboxRow key={item.id} item={item} />
          ))}
        </div>
      )}
    </>
  );

  if (!showHeader) {
    // Page mode: the page supplies the header / chrome; just render the list.
    return (
      <div className="rounded-xl border border-border-light bg-surface-primary overflow-hidden">
        {body}
      </div>
    );
  }

  return (
    <Card className="h-full" padding="none">
      <div className="px-4 pt-4">
        <CardHeader
          title={
            <span className="inline-flex items-center gap-2">
              <InboxIcon size={16} className="text-oe-blue" strokeWidth={1.75} />
              {t('inbox.title', { defaultValue: 'Inbox' })}
              {total > 0 && (
                <Badge variant="blue" size="sm">
                  {total}
                </Badge>
              )}
            </span>
          }
          action={
            <button
              type="button"
              onClick={() => navigate('/inbox')}
              className="inline-flex items-center gap-1 text-xs font-medium text-content-secondary hover:text-oe-blue transition-colors"
            >
              {t('inbox.view_all', { defaultValue: 'View all' })}
              <ArrowRight size={13} />
            </button>
          }
        />
      </div>
      {/* Summary chips - approvals vs alerts at a glance. */}
      {!isLoading && !isError && items.length > 0 && (
        <div className="flex items-center gap-2 px-4 pb-2 text-2xs text-content-tertiary">
          <span className="inline-flex items-center gap-1">
            <ClipboardCheck size={12} className="text-amber-500" />
            {t('inbox.approvals_count', {
              defaultValue: '{{count}} approvals',
              count: approvalsCount,
            })}
          </span>
          <span aria-hidden>·</span>
          <span className="inline-flex items-center gap-1">
            <Bell size={12} className="text-oe-blue" />
            {t('inbox.alerts_count', { defaultValue: '{{count}} alerts', count: alertsCount })}
          </span>
        </div>
      )}
      <CardContent className="!mt-0 !p-0">{body}</CardContent>
    </Card>
  );
}

export default InboxPanel;
