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
import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { BookText, Link2, X } from 'lucide-react';
import { Button } from '@/shared/ui';
import { textCatalogApi, type TextPosition } from './api';

function PickRow({
  position,
  depth,
  selectedId,
  onPick,
}: {
  position: TextPosition;
  depth: number;
  selectedId: string | null;
  onPick: (p: TextPosition) => void;
}) {
  const { t } = useTranslation();
  const isSelected = selectedId === position.id;
  return (
    <>
      <button
        type="button"
        disabled={!position.measurable}
        onClick={() => position.measurable && onPick(position)}
        className={`flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left transition-colors ${
          isSelected
            ? 'bg-oe-blue-subtle/50 ring-1 ring-oe-blue/40'
            : position.measurable
              ? 'hover:bg-surface-secondary'
              : 'cursor-default'
        }`}
        style={{ paddingLeft: `${depth * 18 + 8}px` }}
      >
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
        <PickRow key={c.id} position={c} depth={depth + 1} selectedId={selectedId} onPick={onPick} />
      ))}
    </>
  );
}

export function TextCatalogPickerModal({
  boqId,
  onClose,
  onInserted,
}: {
  boqId: string;
  onClose: () => void;
  onInserted: (summary: { ordinal: string; resourcesCopied: number; assemblyApplied: boolean }) => void;
}) {
  const { t } = useTranslation();
  const [catalogId, setCatalogId] = useState<string | null>(null);
  const [picked, setPicked] = useState<TextPosition | null>(null);
  const [quantity, setQuantity] = useState('0');

  const catalogs = useQuery({
    queryKey: ['neoffice', 'text-catalogs'],
    queryFn: () => textCatalogApi.list(),
  });
  const activeId = catalogId ?? catalogs.data?.[0]?.id ?? null;

  const tree = useQuery({
    queryKey: ['neoffice', 'text-catalog-tree', activeId],
    queryFn: () => textCatalogApi.tree(activeId as string),
    enabled: !!activeId,
  });

  const insert = useMutation({
    mutationFn: () =>
      textCatalogApi.insertIntoBoq(picked!.id, { boq_id: boqId, quantity: quantity || '0' }),
    onSuccess: (res) =>
      onInserted({
        ordinal: res.ordinal,
        resourcesCopied: res.resources_copied,
        assemblyApplied: res.assembly_applied,
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
              setPicked(null);
            }}
          >
            {catalogs.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.code} — {c.name}
              </option>
            ))}
          </select>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
          {tree.isLoading && <div className="h-32 animate-pulse rounded bg-surface-secondary" />}
          {tree.data?.positions.length === 0 && (
            <div className="p-6 text-center text-sm text-content-tertiary">
              {t('text_catalog.empty_catalog', { defaultValue: 'Ce catalogue est vide.' })}
            </div>
          )}
          {tree.data?.positions.map((p) => (
            <PickRow key={p.id} position={p} depth={0} selectedId={picked?.id ?? null} onPick={setPicked} />
          ))}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-border-light px-4 py-3">
          <div className="min-w-0 text-xs text-content-tertiary">
            {picked ? (
              <>
                <span className="font-mono">{picked.code}</span> · {picked.unit}
                {picked.assembly_id && (
                  <> · {t('text_catalog.with_assembly', { defaultValue: 'avec son analyse de prix' })}</>
                )}
              </>
            ) : (
              t('text_catalog.pick_measurable', {
                defaultValue: 'Choisissez une sous-position (celles qui ont une unité).',
              })
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <label className="flex items-center gap-1 text-xs text-content-secondary">
              {t('boq.quantity', { defaultValue: 'Quantité' })}
              <input
                className="w-24 rounded border border-border-light bg-surface-primary px-2 py-1 text-right text-sm tabular-nums"
                inputMode="decimal"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                autoComplete="off"
              />
            </label>
            <Button variant="secondary" onClick={onClose}>
              {t('common.cancel', { defaultValue: 'Annuler' })}
            </Button>
            <Button onClick={() => insert.mutate()} disabled={!picked || insert.isPending}>
              {t('text_catalog.insert', { defaultValue: 'Insérer' })}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
