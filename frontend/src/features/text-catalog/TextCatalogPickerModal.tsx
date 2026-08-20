/**
 * NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OpenConstructionERP.
 *
 * "Insérer depuis le catalogue de descriptions" — pick a CAN/NPK wording and
 * drop it into the devis, bringing its assembly along when one is linked.
 *
 * Only MEASURABLE rows can be inserted: a wording line (no unit) is a heading,
 * not work. It is still shown, greyed and non-clickable, because the estimator
 * navigates by it — hiding it would break the reading order of a CAN page.
 */
import { useCallback, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { BookText, Link2, X } from 'lucide-react';
import { Button } from '@/shared/ui';
import { textCatalogApi, type TextPosition } from './api';

function PickRow({
  position,
  depth,
  selected,
  onToggle,
  onToggleAll,
}: {
  position: TextPosition;
  depth: number;
  selected: Set<string>;
  onToggle: (p: TextPosition) => void;
  onToggleAll: (p: TextPosition) => void;
}) {
  const { t } = useTranslation();
  // //// NEOFFICE PATCH — a wording is selectable now. It used to be disabled
  // on the grounds that it has no unit and cannot be priced, which is true and
  // beside the point: it carries the verb of the CAN item, and the sub-position
  // alone states a thickness without stating what work. Picking it inserts it
  // as a free text line and brings its measurable children underneath.
  // //// END NEOFFICE PATCH
  //// NEOFFICE PATCH — checkboxes, not one pick. Cédric Protti, 2026-08-19:
  //// "Si nous avons besoin d'une seule sous-position, nous devons effacer
  //// manuellement celles qui sont en trop." Checking a wording checks its
  //// children too, because taking a whole CAN item stays the common case —
  //// but each of them can now be unchecked. //// END NEOFFICE PATCH
  const isSelected = selected.has(position.id);
  return (
    <>
      <button
        type="button"
        onClick={() => onToggle(position)}
        className={`flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left transition-colors ${
          isSelected
            ? 'bg-oe-blue-subtle/50 ring-1 ring-oe-blue/40'
            : 'hover:bg-surface-secondary'
        }`}
        style={{ paddingLeft: `${depth * 18 + 8}px` }}
      >
        <input
          type="checkbox"
          checked={isSelected}
          readOnly
          tabIndex={-1}
          className="mt-1 h-3.5 w-3.5 shrink-0 rounded border-border-light"
        />
        <span className="mt-0.5 shrink-0 font-mono text-xs tabular-nums text-content-secondary">
          {position.code}
        </span>
        <span className="min-w-0 flex-1">
          {/* //// NEOFFICE PATCH — a wording line was drawn in the same faint
              grey as a disabled control, and the client reported it as simply
              missing (2026-08-13). It is not missing and it is not disabled
              chrome: it is the sentence its sub-positions complete, and the
              estimator navigates by it. Rendered at normal weight with a rule
              down the left instead, so it reads as a heading rather than as
              something that failed to load. Still not selectable — a wording
              has no unit and cannot become a priced line.
              //// END NEOFFICE PATCH */}
          <span
            className={`block text-sm ${
              position.measurable
                ? 'text-content-primary'
                : 'border-l-2 border-oe-blue/30 pl-2 font-medium text-content-secondary'
            }`}
          >
            {position.title}
          </span>
          {position.body && (
            <span className="block whitespace-pre-wrap text-xs leading-snug text-content-tertiary">
              {position.body}
            </span>
          )}
        </span>
        <span className="flex shrink-0 items-center gap-1.5">
          {/* //// NEOFFICE PATCH — whole-item shortcut, on the wordings that
              have children. Replaces the old always-on cascade. //// END */}
          {position.children.length > 0 && (
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => { e.stopPropagation(); onToggleAll(position); }}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.stopPropagation(); onToggleAll(position); } }}
              className="rounded border border-border-light px-1.5 py-0.5 text-2xs text-content-tertiary hover:border-oe-blue/40 hover:text-oe-blue"
              title={t('text_catalog.pick_all_children', {
                defaultValue: 'Cocher ce libellé et toutes ses sous-positions',
              })}
            >
              {t('text_catalog.pick_all', { defaultValue: 'tout' })}
            </span>
          )}
          {position.assembly_id && (
            <span
              className="inline-flex items-center gap-1 rounded-full bg-oe-blue-subtle/40 px-1.5 py-0.5 text-2xs font-medium text-oe-blue-text"
              title={t('text_catalog.has_assembly', {
                defaultValue: 'Une analyse de prix est liée : elle suivra dans le devis.',
              })}
            >
              <Link2 size={9} />
            </span>
          )}
          {position.measurable ? (
            <span className="rounded-full bg-surface-tertiary px-2 py-0.5 text-2xs text-content-secondary">
              {position.unit}
            </span>
          ) : (
            <span className="text-2xs italic text-content-quaternary">
              {t('text_catalog.wording', { defaultValue: 'libellé' })}
            </span>
          )}
        </span>
      </button>
      {position.children.map((c) => (
        <PickRow key={c.id} position={c} depth={depth + 1} selected={selected} onToggle={onToggle} onToggleAll={onToggleAll} />
      ))}
    </>
  );
}

export function TextCatalogPickerModal({
  boqId,
  onClose,
  onInserted,
  // //// NEOFFICE PATCH — the estimate's chapters, so the picked position can
  // land inside one. Without a parent the row is stored at the root: the grid
  // only draws what sits under a chapter, so it surfaced above the whole
  // estimate, detached from the structure the estimator built.
  sections = [],
  defaultParentId = null,
  // //// END NEOFFICE PATCH
}: {
  boqId: string;
  onClose: () => void;
  sections?: Array<{ id: string; label: string }>;
  defaultParentId?: string | null;
  onInserted: (summary: {
    ordinal: string;
    resourcesCopied: number;
    assemblyApplied: boolean;
    isWording?: boolean;
    childrenInserted?: number;
    assembliesApplied?: number;
  }) => void;
}) {
  const { t } = useTranslation();
  //// NEOFFICE PATCH — reopen on the catalogue last used. Cédric Protti,
  //// 2026-08-20: "il faudrait que la fenêtre s'ouvre sur le dernier catalogue
  //// utilisé". An estimator works a chapter at a time; re-picking it on every
  //// insert is a click that carries no decision.
  const LAST_CATALOG_KEY = 'neoffice.textCatalog.lastId';
  const [catalogId, setCatalogId] = useState<string | null>(() => {
    try { return localStorage.getItem(LAST_CATALOG_KEY); } catch { return null; }
  });
  //// END NEOFFICE PATCH
  //// NEOFFICE PATCH — a set, not one position. And no quantity field:
  //// "les quantités changent toujours […] il est judicieux que les quantités
  //// soient gérées uniquement dans la fenêtre du devis" (Cédric, 2026-08-19).
  //// Rows land at zero and are typed in the grid, next to the others.
  const [selected, setSelected] = useState<Set<string>>(new Set());
  //// END NEOFFICE PATCH
  //// NEOFFICE PATCH — where the position lands. Defaults to the chapter the
  //// estimator is standing in, so the common case needs no extra choice.
  const [parentId, setParentId] = useState<string | null>(
    defaultParentId ?? sections[0]?.id ?? null,
  );
  //// END NEOFFICE PATCH
  //// NEOFFICE PATCH — take the price analysis, or don't. Cédric Protti,
  //// 2026-08-18: "pourquoi les articles du catalogue ne pourraient-ils pas
  //// être insérés avec ou sans l'analyse de prix ?". An estimator who prices
  //// a job by hand does not want ours silently imposed on the row.
  const [withAssembly, setWithAssembly] = useState(true);
  //// END NEOFFICE PATCH

  const catalogs = useQuery({
    queryKey: ['neoffice', 'text-catalogs'],
    queryFn: () => textCatalogApi.list(),
  });
  //// NEOFFICE — a remembered catalogue that no longer exists must not leave the
  //// dialog empty; fall back to the first one.
  const activeId =
    (catalogId && catalogs.data?.some((c) => c.id === catalogId) ? catalogId : null)
    ?? catalogs.data?.[0]?.id
    ?? null;

  const tree = useQuery({
    queryKey: ['neoffice', 'text-catalog-tree', activeId],
    queryFn: () => textCatalogApi.tree(activeId as string),
    enabled: !!activeId,
  });

  //// NEOFFICE PATCH — checking a wording checks its children, unchecking it
  //// releases them. Taking a whole CAN item stays one gesture; keeping only
  //// one sub-position is now also one gesture instead of an insert followed
  //// by deletions. //// END NEOFFICE PATCH
  const toggle = useCallback((p: TextPosition) => {
    setSelected((prev) => {
      const next = new Set(prev);
      //// NEOFFICE PATCH — one row per click, children left alone.
      //// Checking a wording used to check its sub-positions too, on the
      //// grounds that taking a whole CAN item is the common case. Cédric
      //// Protti, 2026-08-20: "lorsqu'on sélectionne un article, l'ensemble des
      //// sous-articles sont sélectionnés. Si il y en a beaucoup, c'est long à
      //// les décocher." Unchecking many is more work than checking a few, and
      //// "Tout cocher" below covers the whole-item case in one gesture.
      //// END NEOFFICE PATCH
      if (next.has(p.id)) next.delete(p.id);
      else next.add(p.id);
      return next;
    });
  }, []);

  //// NEOFFICE PATCH — take the whole CAN item in one click when that IS the
  //// intent, without imposing it on every click. //// END NEOFFICE PATCH
  const toggleWithChildren = useCallback((p: TextPosition) => {
    setSelected((prev) => {
      const next = new Set(prev);
      const ids = [p.id, ...p.children.map((c) => c.id)];
      const allIn = ids.every((id) => next.has(id));
      if (allIn) ids.forEach((id) => next.delete(id));
      else ids.forEach((id) => next.add(id));
      return next;
    });
  }, []);

  const insert = useMutation({
    mutationFn: () =>
      textCatalogApi.insertManyIntoBoq({
        boq_id: boqId,
        parent_id: parentId,
        position_ids: [...selected],
        with_assembly: withAssembly,
      }),
    onSuccess: (res) =>
      onInserted({
        ordinal: res.codes.join(', '),
        resourcesCopied: 0,
        assemblyApplied: res.assemblies_applied > 0,
        childrenInserted: res.inserted,
        assembliesApplied: res.assemblies_applied,
      }),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className="flex max-h-[80vh] w-full max-w-3xl flex-col rounded-xl bg-surface-primary shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border-light px-4 py-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-content-primary">
            <BookText size={16} className="text-oe-blue" />
            {t('text_catalog.insert_title', { defaultValue: 'Insérer depuis le catalogue de descriptions' })}
          </h3>
          <button type="button" onClick={onClose} className="text-content-tertiary hover:text-content-primary">
            <X size={16} />
          </button>
        </div>

        <div className="flex items-center gap-2 border-b border-border-light px-4 py-2">
          <span className="text-xs text-content-secondary">
            {t('text_catalog.catalog', { defaultValue: 'Catalogue' })}
          </span>
          <select
            className="rounded border border-border-light bg-surface-primary px-2 py-1 text-sm"
            value={activeId ?? ''}
            onChange={(e) => {
              setCatalogId(e.target.value);
              try { localStorage.setItem(LAST_CATALOG_KEY, e.target.value); } catch { /* private mode */ }
              setSelected(new Set());
            }}
          >
            {catalogs.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.code} — {c.name}
              </option>
            ))}
          </select>

          {/* //// NEOFFICE PATCH — say, and let the estimator change, where the
              position lands. Silent insertion at the root is what made the
              lines appear above the whole estimate. */}
          {sections.length > 0 && (
            <>
              <span className="ml-3 text-xs text-content-secondary">
                {t('text_catalog.insert_into', { defaultValue: 'Insérer dans' })}
              </span>
              <select
                className="min-w-0 max-w-xs flex-1 truncate rounded border border-border-light bg-surface-primary px-2 py-1 text-sm"
                value={parentId ?? ''}
                onChange={(e) => setParentId(e.target.value || null)}
              >
                {sections.map((sec) => (
                  <option key={sec.id} value={sec.id}>
                    {sec.label}
                  </option>
                ))}
              </select>
            </>
          )}
          {/* //// END NEOFFICE PATCH */}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
          {tree.isLoading && <div className="h-32 animate-pulse rounded bg-surface-secondary" />}
          {tree.data?.positions.length === 0 && (
            <div className="p-6 text-center text-sm text-content-tertiary">
              {t('text_catalog.empty_catalog', { defaultValue: 'Ce catalogue est vide.' })}
            </div>
          )}
          {tree.data?.positions.map((p) => (
            <PickRow key={p.id} position={p} depth={0} selected={selected} onToggle={toggle} onToggleAll={toggleWithChildren} />
          ))}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-border-light px-4 py-3">
          <div className="min-w-0 text-xs text-content-tertiary">
            {selected.size > 0
              ? t('text_catalog.n_selected', {
                  defaultValue: '{{count}} ligne(s) sélectionnée(s) — quantités à saisir dans le devis',
                  count: selected.size,
                })
              : t('text_catalog.pick_measurable', {
                  defaultValue:
                    'Cochez ce que vous voulez insérer. Cocher un libellé coche ses sous-positions.',
                })}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {/* //// NEOFFICE PATCH — opt out of the price analysis. //// END */}
            <label
              className="flex cursor-pointer items-center gap-1.5 text-xs text-content-secondary"
              title={t('text_catalog.with_assembly_hint', {
                defaultValue:
                  "Décochez pour n'insérer que le texte : la ligne arrive sans prix, à chiffrer vous-même.",
              })}
            >
              <input
                type="checkbox"
                checked={withAssembly}
                onChange={(e) => setWithAssembly(e.target.checked)}
                className="h-3.5 w-3.5 rounded border-border-light"
              />
              {t('text_catalog.take_assembly', { defaultValue: 'Avec l’analyse de prix' })}
            </label>
            {/* //// NEOFFICE PATCH — reach the catalogue from where the gap
                is noticed. The estimator discovers a missing or wrong wording
                while inserting, not while browsing a settings page.
                //// END NEOFFICE PATCH */}
            <a
              href="/neoconstruction/text-catalog"
              target="_blank"
              rel="noreferrer"
              className="text-xs text-oe-blue underline-offset-2 hover:underline"
            >
              {t('text_catalog.manage', { defaultValue: 'Éditer le catalogue' })}
            </a>
            <Button variant="secondary" onClick={onClose}>
              {t('common.cancel', { defaultValue: 'Annuler' })}
            </Button>
            <Button onClick={() => insert.mutate()} disabled={selected.size === 0 || insert.isPending}>
              {t('text_catalog.insert', { defaultValue: 'Insérer' })}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
