/**
 * InboxPage - full-page unified approvals/alerts inbox.
 *
 * Linked from the sidebar (Overview group) and the dashboard Inbox widget's
 * "View all". Aggregates the caller's pending approvals (file-approval +
 * change-order approval steps) and unread alerts via
 * ``GET /api/v1/dashboard/inbox/`` - one IDOR-scoped list. The heavy lifting
 * lives in :mod:`InboxPanel`; this page only supplies the standard module top
 * block + a refresh action.
 */
import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/shared/ui';
import { PageHeader } from '@/shared/ui/PageHeader';
import { InboxPanel } from './InboxPanel';

export function InboxPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const handleRefresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['inbox'] });
  }, [queryClient]);

  return (
    <div className="space-y-5">
      <PageHeader
        srTitle={t('inbox.title', { defaultValue: 'Inbox' })}
        subtitle={t('inbox.page_subtitle', {
          defaultValue:
            'Everything waiting on you - pending approvals and alerts from across your projects, in one list.',
        })}
        actions={
          <Button
            variant="secondary"
            size="sm"
            icon={<RefreshCw size={14} />}
            onClick={handleRefresh}
          >
            {t('common.refresh', { defaultValue: 'Refresh' })}
          </Button>
        }
      />
      <InboxPanel limit={100} showHeader={false} />
    </div>
  );
}

export default InboxPage;
