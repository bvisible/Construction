/**
 * NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OpenConstructionERP.
 *
 * Catalogue de descriptions (CAN / NPK).
 *
 * A library of position WORDINGS, which is not the same thing as the cost
 * catalogue: here the parent line carries the text and NO unit, and only its
 * sub-positions are measurable. Written for the way a Swiss estimator reads a
 * CAN page:
 *
 *   135.046  Fourniture et mise en place d'un béton de propreté…
 *     .01    Sous radier / Béton CP 150 0/32 / Epaisseur env. 5 cm     m2
 *
 * A sub-position can carry an assembly, so picking the wording in a devis
 * brings the priced recipe with it.
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { BookText, ChevronDown, ChevronRight, Plus, Trash2, Link2 } from 'lucide-react';
import { Button, Card } from '@/shared/ui';
import { useToastStore } from '@/stores/useToastStore';
import { textCatalogApi, type TextPosition } from './api';

/** One position row and, indented under it, its sub-positions. */
function PositionRow({
  position,
  depth,
  catalogId,
  onChanged,
}: {
  position: TextPosition;
  depth: number;
  catalogId: string;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const addToast = useToastStore((s) => s.addToast);
  const [open, setOpen] = useState(true);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ code: '', title: '', body: '', unit: '' });

  const createSub = useMutation({
    mutationFn: () =>
      textCatalogApi.createPosition(catalogId, {
        code: draft.code || `${position.code}.${String(position.children.length + 1).padStart(2, '0')}`,
        title: draft.title,
        body: draft.body,
        // Empty stays empty: a wording line has no unit, and that is what makes
        // it a wording line rather than a priced article.
        unit: draft.unit.trim() || null,
        parent_id: position.id,
        sort_order: position.children.length + 1,
      }),
    onSuccess: () => {
      setAdding(false);
      setDraft({ code: '', title: '', body: '', unit: '' });
      onChanged();
    },
  });

  const remove = useMutation({
    mutationFn: () => textCatalogApi.deletePosition(position.id),
    onSuccess: () => {
      addToast({ type: 'success', title: t('text_catalog.deleted', { defaultValue: 'Position supprimée' }) });
      onChanged();
    },
  });

  const hasChildren = position.children.length > 0;

  return (
    <div>
      <div
        className="group flex items-start gap-2 rounded-lg px-2 py-1.5 hover:bg-surface-secondary/50"
        style={{ paddingLeft: `${depth * 20 + 8}px` }}
      >
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className={`mt-0.5 text-content-tertiary hover:text-content-primary ${hasChildren ? '' : 'invisible'}`}
          aria-label={open ? 'Replier' : 'Déplier'}
        >
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>

        <span className="mt-0.5 shrink-0 font-mono text-xs tabular-nums text-content-secondary">
          {position.code}
        </span>

        <div className="min-w-0 flex-1">
          <div className="text-sm text-content-primary">{position.title}</div>
          {position.body && (
            // Newlines matter here: a CAN wording is written across lines.
            <div className="whitespace-pre-wrap text-xs leading-snug text-content-tertiary">
              {position.body}
            </div>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {position.measurable ? (
            <span className="rounded-full bg-surface-tertiary px-2 py-0.5 text-2xs font-medium text-content-secondary">
              {position.unit}
            </span>
          ) : (
            <span
              className="text-2xs italic text-content-quaternary"
              title={t('text_catalog.no_unit_hint', {
                defaultValue: 'Ligne de libellé : pas d’unité, donc pas de quantité ni de prix.',
              })}
            >
              {t('text_catalog.wording', { defaultValue: 'libellé' })}
            </span>
          )}
          {position.assembly_id && (
            <span
              className="inline-flex items-center gap-1 rounded-full bg-oe-blue-subtle/40 px-2 py-0.5 text-2xs font-medium text-oe-blue-text"
              title={t('text_catalog.has_assembly', {
                defaultValue: 'Une analyse de prix est liée : elle suivra dans le devis.',
              })}
            >
              <Link2 size={9} />
              {t('text_catalog.assembly', { defaultValue: 'analyse' })}
            </span>
          )}
          <button
            type="button"
            onClick={() => setAdding((v) => !v)}
            className="opacity-0 transition-opacity group-hover:opacity-100 text-content-tertiary hover:text-oe-blue"
            title={t('text_catalog.add_sub', { defaultValue: 'Ajouter une sous-position' })}
          >
            <Plus size={14} />
          </button>
          <button
            type="button"
            onClick={() => remove.mutate()}
            className="opacity-0 transition-opacity group-hover:opacity-100 text-content-tertiary hover:text-red-600"
            title={t('common.delete', { defaultValue: 'Supprimer' })}
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      {adding && (
        <div
          className="mb-2 space-y-2 rounded-lg border border-border-light bg-surface-secondary/40 p-3"
          style={{ marginLeft: `${depth * 20 + 28}px` }}
        >
          <div className="flex gap-2">
            <input
              className="w-32 rounded border border-border-light bg-surface-primary px-2 py-1 font-mono text-xs"
              placeholder={`${position.code}.01`}
              value={draft.code}
              onChange={(e) => setDraft({ ...draft, code: e.target.value })}
              autoComplete="off"
            />
            <input
              className="flex-1 rounded border border-border-light bg-surface-primary px-2 py-1 text-sm"
              placeholder={t('text_catalog.title_ph', { defaultValue: 'Titre — ex. Sous radier' })}
              value={draft.title}
              onChange={(e) => setDraft({ ...draft, title: e.target.value })}
              autoComplete="off"
            />
            <input
              className="w-24 rounded border border-border-light bg-surface-primary px-2 py-1 text-sm"
              placeholder={t('text_catalog.unit_ph', { defaultValue: 'unité' })}
              value={draft.unit}
              onChange={(e) => setDraft({ ...draft, unit: e.target.value })}
              autoComplete="off"
            />
          </div>
          <textarea
            className="w-full rounded border border-border-light bg-surface-primary px-2 py-1 text-xs"
            rows={3}
            placeholder={t('text_catalog.body_ph', {
              defaultValue: 'Descriptif — une ligne par précision\nBéton CP 150 0/32\nEpaisseur env. 5 cm',
            })}
            value={draft.body}
            onChange={(e) => setDraft({ ...draft, body: e.target.value })}
          />
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setAdding(false)}>
              {t('common.cancel', { defaultValue: 'Annuler' })}
            </Button>
            <Button onClick={() => createSub.mutate()} disabled={createSub.isPending}>
              {t('common.add', { defaultValue: 'Ajouter' })}
            </Button>
          </div>
        </div>
      )}

      {open &&
        position.children.map((child) => (
          <PositionRow
            key={child.id}
            position={child}
            depth={depth + 1}
            catalogId={catalogId}
            onChanged={onChanged}
          />
        ))}
    </div>
  );
}

export function TextCatalogPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);
  const [selected, setSelected] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newCatalog, setNewCatalog] = useState({ code: '', name: '' });
  const [rootDraft, setRootDraft] = useState({ code: '', title: '' });
  const [addingRoot, setAddingRoot] = useState(false);

  const catalogs = useQuery({
    queryKey: ['neoffice', 'text-catalogs'],
    queryFn: () => textCatalogApi.list(),
  });

  const activeId = selected ?? catalogs.data?.[0]?.id ?? null;

  const tree = useQuery({
    queryKey: ['neoffice', 'text-catalog-tree', activeId],
    queryFn: () => textCatalogApi.tree(activeId as string),
    enabled: !!activeId,
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['neoffice', 'text-catalog-tree'] });
    qc.invalidateQueries({ queryKey: ['neoffice', 'text-catalogs'] });
  };

  const createCatalog = useMutation({
    mutationFn: () => textCatalogApi.create({ ...newCatalog, standard: 'CAN', language: 'fr' }),
    onSuccess: (c) => {
      setCreating(false);
      setNewCatalog({ code: '', name: '' });
      setSelected(c.id);
      refresh();
      addToast({ type: 'success', title: t('text_catalog.created', { defaultValue: 'Catalogue créé' }) });
    },
  });

  const createRoot = useMutation({
    mutationFn: () =>
      textCatalogApi.createPosition(activeId as string, {
        code: rootDraft.code,
        title: rootDraft.title,
        // No unit: this is the wording line, its sub-positions carry the units.
        unit: null,
        sort_order: (tree.data?.positions.length ?? 0) + 1,
      }),
    onSuccess: () => {
      setAddingRoot(false);
      setRootDraft({ code: '', title: '' });
      refresh();
    },
  });

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-lg font-semibold text-content-primary">
            <BookText size={18} className="text-oe-blue" />
            {t('text_catalog.title', { defaultValue: 'Catalogue de descriptions' })}
          </h1>
          <p className="mt-0.5 text-xs text-content-tertiary">
            {t('text_catalog.subtitle', {
              defaultValue:
                'Bibliothèque de textes de position (CAN / NPK). Une ligne de libellé n’a pas d’unité ; seules ses sous-positions sont mesurables et peuvent porter une analyse de prix.',
            })}
          </p>
        </div>
        <Button onClick={() => setCreating((v) => !v)}>
          <Plus size={14} /> {t('text_catalog.new_catalog', { defaultValue: 'Nouveau catalogue' })}
        </Button>
      </div>

      {creating && (
        <Card padding="md">
          <div className="flex items-end gap-2">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-content-secondary">
                {t('text_catalog.code', { defaultValue: 'Code' })}
              </span>
              <input
                className="w-28 rounded border border-border-light bg-surface-primary px-2 py-1 font-mono text-sm"
                placeholder="135"
                value={newCatalog.code}
                onChange={(e) => setNewCatalog({ ...newCatalog, code: e.target.value })}
                autoComplete="off"
              />
            </label>
            <label className="flex flex-1 flex-col gap-1">
              <span className="text-xs text-content-secondary">
                {t('text_catalog.name', { defaultValue: 'Nom' })}
              </span>
              <input
                className="w-full rounded border border-border-light bg-surface-primary px-2 py-1 text-sm"
                placeholder="Béton et béton armé"
                value={newCatalog.name}
                onChange={(e) => setNewCatalog({ ...newCatalog, name: e.target.value })}
                autoComplete="off"
              />
            </label>
            <Button onClick={() => createCatalog.mutate()} disabled={createCatalog.isPending}>
              {t('common.create', { defaultValue: 'Créer' })}
            </Button>
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[260px_1fr]">
        <Card padding="sm" className="h-fit">
          <div className="mb-2 text-2xs font-semibold uppercase tracking-wide text-content-tertiary">
            {t('text_catalog.catalogs', { defaultValue: 'Catalogues' })}
          </div>
          {catalogs.isLoading && <div className="h-16 animate-pulse rounded bg-surface-secondary" />}
          {catalogs.data?.length === 0 && (
            <div className="text-xs text-content-tertiary">
              {t('text_catalog.empty', { defaultValue: 'Aucun catalogue pour l’instant.' })}
            </div>
          )}
          <ul className="space-y-1">
            {catalogs.data?.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => setSelected(c.id)}
                  className={`w-full rounded-lg px-2 py-1.5 text-left text-sm transition-colors ${
                    activeId === c.id
                      ? 'bg-oe-blue-subtle/40 text-oe-blue-text'
                      : 'text-content-secondary hover:bg-surface-secondary'
                  }`}
                >
                  <span className="font-mono text-xs">{c.code}</span> {c.name}
                  <span className="ml-1 text-2xs text-content-tertiary">({c.position_count})</span>
                </button>
              </li>
            ))}
          </ul>
        </Card>

        <Card padding="sm" className="min-w-0">
          {!activeId && (
            <div className="p-6 text-center text-sm text-content-tertiary">
              {t('text_catalog.pick', { defaultValue: 'Créez ou sélectionnez un catalogue.' })}
            </div>
          )}
          {activeId && tree.isLoading && (
            <div className="h-40 animate-pulse rounded bg-surface-secondary" />
          )}
          {tree.data && (
            <>
              <div className="mb-2 flex items-center justify-between">
                <div className="text-sm font-semibold text-content-primary">
                  <span className="font-mono text-xs text-content-secondary">{tree.data.code}</span>{' '}
                  {tree.data.name}
                </div>
                <Button variant="secondary" onClick={() => setAddingRoot((v) => !v)}>
                  <Plus size={13} /> {t('text_catalog.add_position', { defaultValue: 'Position' })}
                </Button>
              </div>

              {addingRoot && (
                <div className="mb-3 flex items-end gap-2 rounded-lg border border-border-light bg-surface-secondary/40 p-3">
                  <input
                    className="w-32 rounded border border-border-light bg-surface-primary px-2 py-1 font-mono text-xs"
                    placeholder="135.046"
                    value={rootDraft.code}
                    onChange={(e) => setRootDraft({ ...rootDraft, code: e.target.value })}
                    autoComplete="off"
                  />
                  <input
                    className="flex-1 rounded border border-border-light bg-surface-primary px-2 py-1 text-sm"
                    placeholder={t('text_catalog.wording_ph', {
                      defaultValue: 'Libellé de la position (sans unité)',
                    })}
                    value={rootDraft.title}
                    onChange={(e) => setRootDraft({ ...rootDraft, title: e.target.value })}
                    autoComplete="off"
                  />
                  <Button onClick={() => createRoot.mutate()} disabled={createRoot.isPending}>
                    {t('common.add', { defaultValue: 'Ajouter' })}
                  </Button>
                </div>
              )}

              {tree.data.positions.length === 0 ? (
                <div className="p-6 text-center text-sm text-content-tertiary">
                  {t('text_catalog.no_positions', {
                    defaultValue: 'Aucune position. Commencez par le libellé (ex. 135.046), puis ajoutez ses sous-positions.',
                  })}
                </div>
              ) : (
                <div className="divide-y divide-border-light/60">
                  {tree.data.positions.map((p) => (
                    <PositionRow
                      key={p.id}
                      position={p}
                      depth={0}
                      catalogId={tree.data.id}
                      onChanged={refresh}
                    />
                  ))}
                </div>
              )}
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
