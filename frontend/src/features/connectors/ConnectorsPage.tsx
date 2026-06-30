// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Document Connectors - pull files that live in scattered places onto the
// project record. Register a watched folder, then "Sync now" scans it and
// imports each new file as a first-class, searchable project document,
// deduplicated so the same file is never imported twice. Registering and
// syncing require an admin role (they read server-local paths).

import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FolderSync, FolderPlus, RefreshCw, Inbox, HardDrive } from 'lucide-react';
import { Card, Badge, EmptyState, SkeletonTable, DismissibleInfo } from '@/shared/ui';
import { getErrorMessage } from '@/shared/lib/api';
import { useProjectContextStore } from '@/stores/useProjectContextStore';
import { listConnectorSources, createConnectorSource, syncConnectorSource } from './api';
import type { ConnectorSource } from './types';

function lastSyncLabel(
  t: (k: string, o: { defaultValue: string } & Record<string, unknown>) => string,
  source: ConnectorSource,
): string {
  if (!source.last_synced_at || !source.last_result) {
    return t('connectors.never_synced', { defaultValue: 'Not synced yet' });
  }
  const r = source.last_result;
  return t('connectors.last_sync', {
    defaultValue: 'Last sync: {{created}} new, {{duplicate}} duplicate, {{known}} already in',
    created: r.created,
    duplicate: r.duplicate,
    known: r.already_known,
  });
}

function SourceCard({
  source,
  onSync,
  syncing,
}: {
  source: ConnectorSource;
  onSync: (id: string) => void;
  syncing: boolean;
}) {
  const { t } = useTranslation();
  return (
    <Card className="space-y-2 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <HardDrive className="h-4 w-4 shrink-0 text-content-tertiary" />
        <span className="text-sm font-semibold text-content-primary">{source.name}</span>
        <Badge variant="neutral">{source.kind}</Badge>
        {!source.enabled && (
          <Badge variant="warning">{t('connectors.disabled', { defaultValue: 'Disabled' })}</Badge>
        )}
        <button
          type="button"
          onClick={() => onSync(source.id)}
          disabled={syncing}
          className="ms-auto inline-flex items-center gap-1.5 rounded-md bg-oe-blue px-3 py-1.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} />
          {t('connectors.sync_now', { defaultValue: 'Sync now' })}
        </button>
      </div>
      <code className="block truncate rounded bg-surface-secondary px-2 py-1 text-xs text-content-secondary">
        {source.root_path}
      </code>
      <p className="text-xs text-content-tertiary">{lastSyncLabel(t, source)}</p>
    </Card>
  );
}

export function ConnectorsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { projectId: routeProjectId } = useParams();
  const activeProjectId = useProjectContextStore((s) => s.activeProjectId);
  const projectId = routeProjectId ?? activeProjectId ?? '';

  const [name, setName] = useState('');
  const [rootPath, setRootPath] = useState('');

  const sourcesQuery = useQuery({
    queryKey: ['connectors', 'sources', projectId],
    queryFn: () => listConnectorSources(projectId),
    enabled: !!projectId,
    retry: false,
    staleTime: 30_000,
  });

  const createMutation = useMutation({
    mutationFn: () => createConnectorSource(projectId, { name: name.trim(), root_path: rootPath.trim() }),
    onSuccess: () => {
      setName('');
      setRootPath('');
      void queryClient.invalidateQueries({ queryKey: ['connectors', 'sources', projectId] });
    },
  });

  const syncMutation = useMutation({
    mutationFn: (sourceId: string) => syncConnectorSource(sourceId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['connectors', 'sources', projectId] });
    },
  });

  const canAdd = !!projectId && name.trim() !== '' && rootPath.trim() !== '';

  if (!projectId) {
    return (
      <div className="p-4">
        <EmptyState
          icon={<FolderSync className="h-6 w-6" />}
          title={t('connectors.no_project_title', { defaultValue: 'No project selected' })}
          description={t('connectors.no_project_desc', {
            defaultValue: 'Select a project to register inbound document connectors for it.',
          })}
        />
      </div>
    );
  }

  return (
    <div className="space-y-4 p-1">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-content-primary">
          <FolderSync className="h-5 w-5" />
          {t('connectors.title', { defaultValue: 'Document Connectors' })}
        </h1>
        <p className="mt-1 text-sm text-content-secondary">
          {t('connectors.subtitle', {
            defaultValue: 'Bring documents from scattered places onto the project record.',
          })}
        </p>
      </div>

      <DismissibleInfo
        storageKey="connectors-intro"
        title={t('connectors.intro_title', { defaultValue: 'How connectors work' })}
      >
        {t('connectors.intro_body', {
          defaultValue:
            'Point a connector at a folder on the server. Each sync scans it and brings in every new file as a project document, so documents stored outside the system still land on the record and are searchable. Files already imported are skipped, and two copies of the same file are detected and not duplicated.',
        })}
      </DismissibleInfo>

      <Card className="space-y-3 p-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-content-primary">
          <FolderPlus className="h-4 w-4" />
          {t('connectors.add_title', { defaultValue: 'Add a watched folder' })}
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-sm text-content-secondary">
            {t('connectors.name', { defaultValue: 'Name' })}
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t('connectors.name_ph', { defaultValue: 'Site drop folder' })}
              className="rounded-md border border-border-light bg-surface-primary px-2 py-1 text-sm text-content-primary"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-content-secondary">
            {t('connectors.root_path', { defaultValue: 'Folder path (on the server)' })}
            <input
              value={rootPath}
              onChange={(e) => setRootPath(e.target.value)}
              placeholder={t('connectors.root_path_ph', { defaultValue: '/data/inbound/site-a' })}
              className="rounded-md border border-border-light bg-surface-primary px-2 py-1 text-sm text-content-primary"
            />
          </label>
        </div>

        {createMutation.isError && (
          <p className="text-sm text-red-600">{getErrorMessage(createMutation.error)}</p>
        )}

        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={!canAdd || createMutation.isPending}
            onClick={() => createMutation.mutate()}
            className="inline-flex items-center gap-1.5 rounded-md bg-oe-blue px-3 py-1.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            <FolderPlus className="h-4 w-4" />
            {t('connectors.add_source', { defaultValue: 'Add connector' })}
          </button>
          <span className="text-xs text-content-tertiary">
            {t('connectors.admin_hint', { defaultValue: 'Registering and syncing a connector require an admin role.' })}
          </span>
        </div>
      </Card>

      {syncMutation.isError && (
        <p className="text-sm text-red-600">{getErrorMessage(syncMutation.error)}</p>
      )}

      <div className="space-y-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-content-primary">
          <FolderSync className="h-4 w-4" />
          {t('connectors.sources', { defaultValue: 'Connectors' })}
        </h2>

        {sourcesQuery.isLoading ? (
          <SkeletonTable rows={2} />
        ) : sourcesQuery.isError ? (
          <EmptyState
            icon={<Inbox className="h-6 w-6" />}
            title={t('connectors.error_title', { defaultValue: 'Could not load connectors' })}
            description={getErrorMessage(sourcesQuery.error)}
          />
        ) : !sourcesQuery.data || sourcesQuery.data.length === 0 ? (
          <EmptyState
            icon={<FolderSync className="h-6 w-6" />}
            title={t('connectors.empty_title', { defaultValue: 'No connectors yet' })}
            description={t('connectors.empty_desc', {
              defaultValue: 'Add a watched folder above to start bringing its documents onto the record.',
            })}
          />
        ) : (
          <div className="space-y-3">
            {sourcesQuery.data.map((source) => (
              <SourceCard
                key={source.id}
                source={source}
                onSync={(id) => syncMutation.mutate(id)}
                syncing={syncMutation.isPending && syncMutation.variables === source.id}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default ConnectorsPage;
