/**
 * Pure, framework-free helpers for the unified inbox.
 *
 * Kept separate from the React components so the ordering / grouping / title
 * derivation can be unit-tested with vitest and reused without pulling in the
 * component tree. No imports from React or the API client here.
 */
import type { InboxItem, InboxSeverity } from './api';

/** Severity rank - higher sorts first when timestamps tie. */
export const SEVERITY_RANK: Record<InboxSeverity, number> = {
  critical: 3,
  warning: 2,
  info: 1,
};

/** Clamp an arbitrary string to one of the three known severities. */
export function normalizeSeverity(value: string | null | undefined): InboxSeverity {
  if (value === 'critical' || value === 'warning' || value === 'info') return value;
  return 'info';
}

/**
 * Deterministic newest-first ordering with a severity then id tiebreak.
 *
 * The backend already sorts, but re-sorting client-side is a cheap safety net
 * (e.g. if items from two cached pages are ever concatenated) and keeps the
 * ordering logic unit-testable. ``created_at`` is compared lexicographically:
 * for the ISO-8601 UTC strings every source emits, that is chronological.
 * Missing timestamps sort last. Pure: does not mutate the input array.
 */
export function sortInboxItems(items: readonly InboxItem[]): InboxItem[] {
  return [...items].sort((a, b) => {
    const ca = a.created_at ?? '';
    const cb = b.created_at ?? '';
    if (ca !== cb) return ca < cb ? 1 : -1; // newest (greater string) first
    const sa = SEVERITY_RANK[normalizeSeverity(a.severity)];
    const sb = SEVERITY_RANK[normalizeSeverity(b.severity)];
    if (sa !== sb) return sb - sa; // higher severity first
    // Fully deterministic final tiebreak on id.
    if (a.id !== b.id) return a.id < b.id ? 1 : -1;
    return 0;
  });
}

/** Count how many items are pending approvals (vs alerts). */
export function countApprovals(items: readonly InboxItem[]): number {
  return items.reduce((n, it) => (it.kind === 'approval' ? n + 1 : n), 0);
}

/**
 * Resolve the display title for an item.
 *
 * Returns ``{ key, defaultValue }`` so the caller can feed it straight into
 * i18next's ``t(key, { defaultValue, ...ctx })``. When the item carries an
 * i18n ``title_key`` we use it (with ``title`` as the English fallback); a
 * missing key degrades to the raw ``title`` string, and a totally empty item
 * degrades to a generic label key. Never returns an empty key (i18next
 * ``t('')`` is a no-op that renders blank).
 */
export function resolveTitle(item: Pick<InboxItem, 'title' | 'title_key'>): {
  key: string;
  defaultValue: string;
} {
  const key =
    typeof item.title_key === 'string' && item.title_key.trim().length > 0
      ? item.title_key
      : '';
  const fallback =
    typeof item.title === 'string' && item.title.trim().length > 0 ? item.title : '';
  if (key) {
    return { key, defaultValue: fallback || key };
  }
  if (fallback) {
    // No i18n key - render the literal title via a stable passthrough key so
    // i18next still receives a non-empty key.
    return { key: 'inbox.item_title_raw', defaultValue: fallback };
  }
  return { key: 'inbox.item_untitled', defaultValue: 'Action required' };
}

/**
 * Human "x ago" string. Takes the i18next ``t`` so the units are localised.
 *
 * Mirrors the NotificationBell formatter; extracted here so the inbox panel
 * and any future surface share one implementation. Returns an empty string
 * for a missing / unparseable timestamp (callers can then omit the row's
 * time element entirely).
 */
export function formatTimeAgo(
  dateStr: string | null | undefined,
  t: (key: string, opts?: Record<string, unknown>) => string,
  now: number = Date.now(),
): string {
  if (!dateStr) return '';
  const ms = new Date(dateStr).getTime();
  if (!Number.isFinite(ms)) return '';
  const diff = now - ms;
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return t('notifications.just_now', { defaultValue: 'Just now' });
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60)
    return t('time.minutes_ago', { defaultValue: '{{count}}m ago', count: minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t('time.hours_ago', { defaultValue: '{{count}}h ago', count: hours });
  const days = Math.floor(hours / 24);
  return t('time.days_ago', { defaultValue: '{{count}}d ago', count: days });
}
