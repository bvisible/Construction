import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import {
  groupPositionsIntoSections,
  isSection,
  type Position,
} from './api';
import { resourceAwareTotalInBase } from './boqHelpers';
import { toDisplayQuantity, toDisplayRate } from '@/shared/lib/unitConversion';

/* ── Types ──────────────────────────────────────────────────────────────── */

export interface PdfMarkupTotal {
  name: string;
  percentage: number;
  amount: number;
}

export interface PdfReportOptions {
  /** BOQ title shown in the report header. */
  boqTitle: string;
  /** Optional project name shown on the cover page. */
  projectName?: string;
  /** Optional date string (ISO or display); defaults to today. */
  date?: string;
  /** Currency symbol prepended in display (e.g. "€", "$"). */
  currency: string;
  /** Flat list of all BOQ positions (sections + items). */
  positions: Position[];
  /** Applied markups with pre-computed amounts. */
  markupTotals: PdfMarkupTotal[];
  /** Direct cost (sum of all line-item totals). */
  directCost: number;
  /** Net total after markups. */
  netTotal: number;
  /** VAT rate as decimal (e.g. 0.19 for 19%). */
  vatRate: number;
  /** VAT amount (pre-computed). */
  vatAmount: number;
  /** Gross total including VAT (pre-computed). */
  grossTotal: number;
  /** BCP-47 locale tag for number formatting (e.g. "en-US", "de-DE"). */
  locale?: string;
  /**
   * Issue #150 — project base currency (ISO 4217) + FX rates. When supplied,
   * every section subtotal and per-position Total is converted into the base
   * currency using the SAME resource-currency-aware conversion the editor
   * grid uses (so a foreign-currency resource prints at its base value, not
   * summed as "1 foreign = 1 base"). Omitted ⇒ totals print verbatim
   * (backward compatible — single-currency BOQs are unaffected).
   */
  baseCurrency?: string;
  fxRates?: Array<{ currency: string; rate: number }>;
  /**
   * Issue #270 - the user's measurement-system preference. When 'imperial'
   * the physical quantity numbers and their unit labels are converted at the
   * print boundary (m -> ft, m2 -> ft2, kg -> lb ...); money (unit rate /
   * total) is per-unit and is NEVER converted. Defaults to 'metric', which
   * passes values through unchanged with tidy unit labels, so stored data is
   * untouched and metric users see identical output to before.
   */
  measurementSystem?: 'metric' | 'imperial';
  // NEOFFICE — export content toggles (from the export menu). Default: shown.
  //  showPrices    false ⇒ a blank bordereau (quantities only, prices empty).
  //  showBreakdown the analyse-de-prix resource sub-rows.
  //  showMetre     the "» Métré sur plan …" provenance sub-rows.
  showPrices?: boolean;
  showBreakdown?: boolean;
  showMetre?: boolean;
}

/** NEOFFICE — what a devis export includes; chosen in the export menu. */
export interface DevisExportContent {
  showPrices: boolean;
  showBreakdown: boolean;
  showMetre: boolean;
}

/** FX context shared between {@link buildSectionGroups} and the renderers. */
interface PdfFxOpts {
  baseCurrency?: string;
  fxRates?: Array<{ currency: string; rate: number }>;
}

/**
 * Issue #150 — per-position Total converted into the project base currency
 * when FX context is present. Mirrors the editor grid's Total column and the
 * Excel export so all three surfaces agree. With no base currency it returns
 * the raw stored total (coerced), preserving the prior PDF behaviour.
 */
function positionTotalForPdf(pos: Position, fx: PdfFxOpts): number {
  if (!fx.baseCurrency) return Number(pos.total) || 0;
  return resourceAwareTotalInBase(
    pos as unknown as {
      total?: number | string | null;
      quantity?: number | string | null;
      metadata?: Record<string, unknown> | null;
      metadata_?: Record<string, unknown> | null;
    },
    fx.baseCurrency,
    fx.fxRates,
  );
}

/* ── Internal section data ──────────────────────────────────────────────── */

interface SectionEntry {
  ordinal: string;
  description: string;
  subtotal: number;
  pageNumber: number; // filled after rendering
}

/* ── Helpers ────────────────────────────────────────────────────────────── */

/**
 * Groups a flat positions array into sections with their children and
 * computes per-section subtotals. Also returns any ungrouped line items.
 * This is a pure function and is exported for unit testing.
 */
export function buildSectionGroups(
  positions: Position[],
  fxOpts?: PdfFxOpts,
): {
  sections: Array<{ ordinal: string; description: string; children: Position[]; subtotal: number }>;
  ungrouped: Position[];
} {
  const grouped = groupPositionsIntoSections(positions, fxOpts);
  return {
    sections: grouped.sections.map((g) => ({
      ordinal: g.section.ordinal,
      description: g.section.description,
      children: g.children,
      subtotal: g.subtotal,
    })),
    ungrouped: grouped.ungrouped.filter((p) => !isSection(p)),
  };
}

// NEOFFICE — jsPDF's core Helvetica is WinAnsi (CP1252); the narrow/no-break
// spaces locales like fr-CH use as a thousands separator are not in CP1252 and
// render as a stray glyph ("2 025" → "2 /025"). Fold them to a plain space.
const asciiSep = (s: string): string => s.replace(/[     ]/g, ' ');

/** Format a number with currency symbol and locale-aware separators. */
function formatCurrency(value: number, currency: string, locale: string): string {
  try {
    const formatted = new Intl.NumberFormat(locale, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
    return asciiSep(`${currency}${formatted}`);
  } catch {
    return `${currency}${value.toFixed(2)}`;
  }
}

/** Format a plain number (for quantities). */
function formatNumber(value: number, locale: string): string {
  try {
    return asciiSep(new Intl.NumberFormat(locale, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value));
  } catch {
    return value.toFixed(2);
  }
}

// //// NEOFFICE PATCH — Cédric's SIA rule: the number of decimals on a quantity
// depends on its unit. bloc / pce = 0, volume (m3) = 3, everything else
// (length / surface / weight) = 2.
function siaFractionDigits(unit: string): number {
  const u = (unit ?? '').toLowerCase().replace(/[.\s]/g, '');
  if (['bloc', 'blocs', 'pce', 'pces', 'pc', 'p', 'pièce', 'piece', 'u', 'ff', 'forfait', 'glob'].includes(u)) return 0;
  if (u.includes('³') || u.endsWith('m3') || u === 'mc') return 3;
  return 2;
}
function formatQuantity(value: number, unit: string, locale: string): string {
  const d = siaFractionDigits(unit);
  try {
    return asciiSep(
      new Intl.NumberFormat(locale, { minimumFractionDigits: d, maximumFractionDigits: d }).format(value),
    );
  } catch {
    return value.toFixed(d);
  }
}

/** Format a date string or Date to a human-readable display string. */
function formatDate(dateInput: string | undefined, locale: string): string {
  const d = dateInput ? new Date(dateInput) : new Date();
  if (isNaN(d.getTime())) return dateInput ?? '';
  try {
    return d.toLocaleDateString(locale, { year: 'numeric', month: 'long', day: 'numeric' });
  } catch {
    return d.toISOString().split('T')[0] ?? '';
  }
}

// //// NEOFFICE PATCH — the priced-devis PDF was emitted with hard-coded English
// labels ("Bill of Quantities", "Qty", "Gross Total"…). The export only carries a
// `locale`, not the i18n `t()`, so localise the headings here: French for the CH
// instance (Cédric), English fallback for every other locale (no regression).
function reportLabels(locale: string) {
  const fr = (locale ?? '').toLowerCase().startsWith('fr');
  return fr
    ? {
        // NEOFFICE — Cédric Protti's imposed devis vocabulary (Pos. / Description
        // / Un. / Prix / Montant) so the export reads exactly like his devis.
        title: 'Devis estimatif', summaryTitle: 'Récapitulatif',
        no: 'Pos.', description: 'Description', unit: 'Un.', qty: 'Quantité',
        unitRate: 'Prix', total: 'Montant',
        ungrouped: 'Postes sans chapitre', sectionSubtotal: 'Sous-total',
        date: 'Date', sections: 'Chapitres', positions: 'Postes', resources: 'Ressources',
        directCost: 'Coût direct', markups: 'Majorations', none: 'Aucune',
        netTotal: 'Total HT', vat: 'TVA', grossTotal: 'Total TTC',
        preparedBy: 'Établi par :', approvedBy: 'Approuvé par :',
        signatureLine: 'Nom / Signature / Date',
        section: 'Chapitre', subtotal: 'Sous-total', item: 'Poste', amount: 'Montant',
      }
    : {
        title: 'Bill of Quantities', summaryTitle: 'Cost Summary',
        no: 'No.', description: 'Description', unit: 'Unit', qty: 'Qty',
        unitRate: 'Unit Rate', total: 'Total',
        ungrouped: 'Ungrouped Items', sectionSubtotal: 'Section Subtotal',
        date: 'Date', sections: 'Sections', positions: 'Positions', resources: 'Resources',
        directCost: 'Direct Cost', markups: 'Markups', none: 'None',
        netTotal: 'Net Total', vat: 'VAT', grossTotal: 'Gross Total',
        preparedBy: 'Prepared by:', approvedBy: 'Approved by:',
        signatureLine: 'Name / Signature / Date',
        section: 'Section', subtotal: 'Subtotal', item: 'Item', amount: 'Amount',
      };
}

/**
 * NEOFFICE — "métré" provenance line for a costed position: shows HOW the
 * quantity was obtained — an annotated pré-métré formula kept on the cell, or a
 * measurement taken on a plan via the Takeoff — so the priced devis reads like
 * Cédric's "devis avec métrés". Returns null for a hand-typed quantity (nothing
 * to justify). Pure; consumes the same metadata the editor grid + takeoff stamp.
 */
function metreLineForPosition(
  p: Position,
  measurementSystem: 'metric' | 'imperial',
  locale: string,
): string | null {
  const meta = (p.metadata ?? (p as unknown as Record<string, unknown>).metadata_) as
    | Record<string, unknown>
    | undefined;
  if (!meta) return null;
  // 1) Pré-métré — an annotated quantity formula kept on the cell (ƒx badge).
  const formula = (meta.formula ?? meta.quantity_formula) as string | undefined;
  if (typeof formula === 'string' && formula.trim()) {
    const dq = toDisplayQuantity(Number(p.quantity), p.unit, measurementSystem);
    return `Pré-métré : ${formula.trim()} = ${formatNumber(dq.value, locale)} ${dq.unit}`;
  }
  // 2) Takeoff — quantity measured on a plan (provenance stamped on push).
  const measured = (meta.measured_value ?? meta.takeoff_value) as number | string | undefined;
  if (p.source === 'takeoff' || measured != null) {
    const plan = (meta.takeoff_document ?? meta.document) as string | undefined;
    const page = (meta.takeoff_page ?? meta.page) as number | string | undefined;
    const unit = (meta.measured_unit as string | undefined) ?? p.unit;
    const where = [`plan${plan ? ` ${plan}` : ''}`, page != null ? `p.${page}` : '']
      .filter(Boolean)
      .join(', ');
    const val = measured != null ? ` : ${formatNumber(Number(measured), locale)} ${unit}` : '';
    return `Métré sur ${where}${val}`;
  }
  return null;
}

/* ── Brand colours ──────────────────────────────────────────────────────── */

const BRAND_DARK = [15, 23, 42] as [number, number, number];     // slate-900
const BRAND_MID = [71, 85, 105] as [number, number, number];     // slate-600
const BRAND_LIGHT = [226, 232, 240] as [number, number, number]; // slate-200
const BRAND_ACCENT = [99, 102, 241] as [number, number, number]; // indigo-500
const WHITE = [255, 255, 255] as [number, number, number];

/* ── Cover page ─────────────────────────────────────────────────────────── */

function renderCoverPage(
  doc: jsPDF,
  options: PdfReportOptions,
  locale: string,
): void {
  const pageW = doc.internal.pageSize.getWidth();
  const pageH = doc.internal.pageSize.getHeight();

  // Background header block
  doc.setFillColor(...BRAND_DARK);
  doc.rect(0, 0, pageW, 80, 'F');

  // Accent stripe
  doc.setFillColor(...BRAND_ACCENT);
  doc.rect(0, 78, pageW, 3, 'F');

  // Wordmark
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(11);
  doc.setTextColor(...WHITE);
  doc.text('Neoconstruction', 20, 20);

  // BOQ title
  doc.setFontSize(26);
  doc.setFont('helvetica', 'bold');
  const titleLines = doc.splitTextToSize(options.boqTitle, pageW - 40) as string[];
  doc.text(titleLines, 20, 45);

  // Project name
  if (options.projectName) {
    doc.setFontSize(13);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(...BRAND_LIGHT);
    doc.text(options.projectName, 20, 68);
  }

  // ── Meta block below header ───────────────────────────────────────────
  doc.setTextColor(...BRAND_DARK);

  const itemCount = options.positions.filter((p) => !isSection(p)).length;
  const sectionCount = buildSectionGroups(options.positions).sections.length;
  const resourceCount = options.positions.reduce((sum, p) => {
    const meta = p.metadata ?? (p as unknown as Record<string, unknown>).metadata_;
    const res = meta && Array.isArray((meta as Record<string, unknown>).resources)
      ? ((meta as Record<string, unknown>).resources as unknown[]).length : 0;
    return sum + res;
  }, 0);

  const metaY = 96;
  const labelX = 20;
  const valueX = 72;

  // Section divider
  doc.setDrawColor(...BRAND_LIGHT);
  doc.setLineWidth(0.4);
  doc.line(labelX, metaY - 4, pageW - 20, metaY - 4);

  const L = reportLabels(locale);
  // NEOFFICE — a price-free export (bordereau) hides every cost figure.
  const showPrices = options.showPrices !== false;
  const metaItems: Array<[string, string]> = [
    [L.date, formatDate(options.date, locale)],
    [L.sections, String(sectionCount)],
    [L.positions, String(itemCount)],
    ...(resourceCount > 0 ? [[L.resources, String(resourceCount)] as [string, string]] : []),
    ...(showPrices
      ? [
          [L.directCost, formatCurrency(options.directCost, options.currency, locale)] as [string, string],
          [L.markups, options.markupTotals.map((m) => `${m.name} ${m.percentage}%`).join(', ') || L.none] as [string, string],
          [L.netTotal, formatCurrency(options.netTotal, options.currency, locale)] as [string, string],
          [L.vat, `${(options.vatRate * 100).toFixed(0)}% (${formatCurrency(options.vatAmount, options.currency, locale)})`] as [string, string],
        ]
      : []),
  ];

  doc.setFontSize(9);
  for (let i = 0; i < metaItems.length; i++) {
    const item = metaItems[i]!;
    const y = metaY + i * 10;
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(...BRAND_MID);
    doc.text(item[0], labelX, y);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(...BRAND_DARK);
    doc.text(item[1], valueX, y);
  }

  // Gross total — highlighted (NEOFFICE: only when prices are shown)
  if (showPrices) {
    const grossY = metaY + metaItems.length * 10 + 4;
    doc.setDrawColor(...BRAND_LIGHT);
    doc.line(labelX, grossY - 4, pageW - 20, grossY - 4);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(12);
    doc.setTextColor(...BRAND_ACCENT);
    doc.text(L.grossTotal, labelX, grossY + 2);
    doc.text(formatCurrency(options.grossTotal, options.currency, locale), valueX, grossY + 2);
  }

  // ── Signature block ─────────────────────────────────────────────────
  const sigY = pageH - 55;
  doc.setDrawColor(...BRAND_LIGHT);
  doc.setLineWidth(0.3);
  doc.line(labelX, sigY, pageW - 20, sigY);

  doc.setFontSize(8);
  doc.setTextColor(...BRAND_MID);
  doc.setFont('helvetica', 'normal');
  doc.text(L.preparedBy, labelX, sigY + 10);
  doc.text(L.approvedBy, pageW / 2, sigY + 10);
  doc.line(labelX, sigY + 28, labelX + 60, sigY + 28);
  doc.line(pageW / 2, sigY + 28, pageW / 2 + 60, sigY + 28);
  doc.text(L.signatureLine, labelX, sigY + 33);
  doc.text(L.signatureLine, pageW / 2, sigY + 33);

  // Footer attribution
  doc.setFontSize(7);
  doc.setTextColor(...BRAND_MID);
  doc.text('Neoconstruction', labelX, pageH - 10);
}

/* ── Table of Contents ──────────────────────────────────────────────────── */

function renderTableOfContents(
  doc: jsPDF,
  sections: SectionEntry[],
): void {
  const pageW = doc.internal.pageSize.getWidth();

  // Section heading
  doc.setFillColor(...BRAND_DARK);
  doc.rect(0, 0, pageW, 18, 'F');
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(13);
  doc.setTextColor(...WHITE);
  doc.text('Table of Contents', 20, 12);

  doc.setTextColor(...BRAND_DARK);

  let y = 32;
  doc.setFontSize(9);
  for (const sec of sections) {
    doc.setFont('helvetica', 'normal');
    const label = `${sec.ordinal}  ${sec.description}`.trim();
    const lines = doc.splitTextToSize(label, pageW - 80) as string[];
    doc.text(lines, 20, y);

    // Dot leaders
    const textW = doc.getTextWidth(lines[0] ?? '');
    const dotsStart = 20 + textW + 2;
    const dotsEnd = pageW - 35;
    doc.setTextColor(...BRAND_LIGHT);
    const dotStr = '.'.repeat(Math.max(0, Math.floor((dotsEnd - dotsStart) / 2)));
    doc.text(dotStr, dotsStart, y);
    doc.setTextColor(...BRAND_DARK);

    // Page reference (filled post-render; placeholder during TOC pass)
    doc.setFont('helvetica', 'bold');
    doc.text(String(sec.pageNumber || '—'), pageW - 30, y, { align: 'right' });
    doc.setFont('helvetica', 'normal');

    y += lines.length * 6 + 2;
    if (y > doc.internal.pageSize.getHeight() - 25) {
      doc.addPage();
      y = 20;
    }
  }
}

/* ── Page footer ────────────────────────────────────────────────────────── */

function addPageFooters(doc: jsPDF, options: PdfReportOptions): void {
  const totalPages = (doc.internal as unknown as { getNumberOfPages: () => number }).getNumberOfPages();
  const pageW = doc.internal.pageSize.getWidth();
  const pageH = doc.internal.pageSize.getHeight();

  for (let i = 1; i <= totalPages; i++) {
    doc.setPage(i);
    doc.setDrawColor(...BRAND_LIGHT);
    doc.setLineWidth(0.3);
    doc.line(15, pageH - 12, pageW - 15, pageH - 12);
    doc.setFontSize(7.5);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(...BRAND_MID);
    doc.text(options.boqTitle, 15, pageH - 7);
    // NEOFFICE — "Page X de Y" for the French/Protti devis, "of" elsewhere.
    const pageWord = (options.locale ?? '').toLowerCase().startsWith('fr') ? 'de' : 'of';
    doc.text(`Page ${i} ${pageWord} ${totalPages}`, pageW - 15, pageH - 7, { align: 'right' });
  }
}

/* ── BOQ table per section ──────────────────────────────────────────────── */

function renderBOQTables(
  doc: jsPDF,
  options: PdfReportOptions,
  locale: string,
  sectionEntries: SectionEntry[],
): void {
  const fxOpts: PdfFxOpts = { baseCurrency: options.baseCurrency, fxRates: options.fxRates };
  const { sections, ungrouped } = buildSectionGroups(options.positions, fxOpts);
  const pageW = doc.internal.pageSize.getWidth();
  // Issue #270 - convert the physical quantity column + its unit label into
  // the user's measurement system at this print boundary only. Money columns
  // (Unit Rate / Total) stay verbatim. Default 'metric' = pass-through.
  const measurementSystem = options.measurementSystem ?? 'metric';
  const L = reportLabels(locale);
  // NEOFFICE — export content toggles (default: everything shown).
  const showPrices = options.showPrices !== false;
  const showBreakdown = options.showBreakdown !== false;
  const showMetre = options.showMetre !== false;

  // Section heading bar
  doc.setFillColor(...BRAND_DARK);
  doc.rect(0, 0, pageW, 18, 'F');
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(13);
  doc.setTextColor(...WHITE);
  // NEOFFICE — Protti header: the devis's own name/number on the left, plus the
  // date on the right, so each page reads like Cédric's "Devis estimatif … · <date>".
  doc.text(options.boqTitle || L.title, 20, 12);
  doc.setFontSize(9.5);
  doc.setFont('helvetica', 'normal');
  doc.text(formatDate(options.date, locale), pageW - 20, 11.5, { align: 'right' });
  doc.setTextColor(...BRAND_DARK);

  let currentY = 26;

  const headerStyles: Parameters<typeof autoTable>[1]['headStyles'] = {
    fillColor: BRAND_DARK,
    textColor: WHITE,
    fontStyle: 'bold',
    fontSize: 8,
  };

  const renderSection = (
    ordinal: string,
    description: string,
    children: Position[],
    subtotal: number,
  ) => {
    // Section title row
    const sectionLabel = `${ordinal}  ${description}`.trim();
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(9);
    doc.setTextColor(...BRAND_ACCENT);

    const labelLines = doc.splitTextToSize(sectionLabel, pageW - 40) as string[];
    doc.text(labelLines, 15, currentY);
    currentY += labelLines.length * 5 + 2;

    const body: string[][] = [];
    for (const p of children) {
      // //// NEOFFICE PATCH — a libellé/description row (Cédric's "jaune") has no
      // unit: show only its number + wording, never a "0.00" quantity or price.
      if (!(p.unit ?? '').toString().trim()) {
        body.push([p.ordinal, p.description, '', '', '', '']);
        continue;
      }
      const pDq = toDisplayQuantity(Number(p.quantity), p.unit, measurementSystem);
      body.push([
        p.ordinal,
        p.description,
        pDq.unit,
        // NEOFFICE — SIA decimals by unit (bloc/pce 0, m3 3, else 2).
        formatQuantity(pDq.value, pDq.unit, locale),
        // Issue #270 - when the quantity is shown converted, the per-unit rate
        // must be restated against the SAME displayed unit so the line still
        // reconciles (qty * rate == Total). The money Total is invariant.
        showPrices ? formatCurrency(toDisplayRate(p.unit_rate, p.unit, measurementSystem), options.currency, locale) : '',
        // Issue #150 — Total converted to base currency (mirrors grid).
        showPrices ? formatCurrency(positionTotalForPdf(p, fxOpts), options.currency, locale) : '',
      ]);
      // //// NEOFFICE PATCH — métré provenance sub-row: show HOW the quantity
      // was obtained (an annotated pré-métré formula, or a measurement taken on
      // a plan via the Takeoff) so the priced devis reads like Cédric's "devis
      // avec métrés". Nothing is printed for a hand-typed quantity.
      const metreLine = showMetre ? metreLineForPosition(p, measurementSystem, locale) : null;
      if (metreLine) {
        // NEOFFICE — use a CP1252-renderable marker (»); jsPDF's core Helvetica
        // can't draw "→" (U+2192) and prints a stray glyph instead.
        body.push(['', `  » ${metreLine}`, '', '', '', '']);
      }
      // //// END NEOFFICE PATCH
      // Add resource sub-rows
      const meta = p.metadata ?? (p as unknown as Record<string, unknown>).metadata_;
      const resources = (showBreakdown && meta && Array.isArray((meta as Record<string, unknown>).resources))
        ? (meta as Record<string, unknown>).resources as Array<{ name: string; type: string; unit: string; quantity: number; unit_rate: number; total?: number }>
        : [];
      for (const r of resources) {
        const rTotal = r.total ?? r.quantity * r.unit_rate;
        const rDq = toDisplayQuantity(Number(r.quantity), r.unit, measurementSystem);
        body.push([
          '',
          `  \u00b7 ${r.name}`, // NEOFFICE \u2014 middle dot; "\u2514" (U+2514) is not in CP1252 (jsPDF Helvetica)
          rDq.unit,
          formatNumber(rDq.value, locale),
          // Reciprocal rate so the resource sub-row reconciles too (see above).
          showPrices ? formatCurrency(toDisplayRate(r.unit_rate, r.unit, measurementSystem), options.currency, locale) : '',
          showPrices ? formatCurrency(rTotal, options.currency, locale) : '',
        ]);
      }
    }

    autoTable(doc, {
      startY: currentY,
      head: [[L.no, L.description, L.unit, L.qty, L.unitRate, L.total]],
      body,
      headStyles: headerStyles,
      bodyStyles: { fontSize: 8, textColor: BRAND_DARK },
      alternateRowStyles: { fillColor: [248, 250, 252] as [number, number, number] },
      columnStyles: {
        0: { cellWidth: 18, fontStyle: 'bold' },
        1: { cellWidth: 'auto' },
        2: { cellWidth: 16, halign: 'center' },
        3: { cellWidth: 22, halign: 'right' },
        4: { cellWidth: 28, halign: 'right' },
        5: { cellWidth: 28, halign: 'right', fontStyle: 'bold' },
      },
      margin: { left: 15, right: 15 },
      theme: 'grid',
      tableLineColor: BRAND_LIGHT,
      tableLineWidth: 0.2,
      didDrawPage: () => {
        // Reset current Y after page break inside autoTable
      },
    });

    const tableEndY = (doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY;

    // Subtotal row — NEOFFICE: only when prices are shown (a bordereau has none).
    const subtotalY = tableEndY + 2;
    if (showPrices) {
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(8.5);
      doc.setTextColor(...BRAND_MID);
      const subtotalText = `${L.sectionSubtotal}: ${formatCurrency(subtotal, options.currency, locale)}`;
      doc.text(subtotalText, pageW - 15, subtotalY, { align: 'right' });
      doc.setDrawColor(...BRAND_ACCENT);
      doc.setLineWidth(0.4);
      doc.line(pageW - 15 - doc.getTextWidth(subtotalText) - 2, subtotalY + 1, pageW - 15, subtotalY + 1);
    }

    currentY = subtotalY + (showPrices ? 10 : 4);
    if (currentY > doc.internal.pageSize.getHeight() - 35) {
      doc.addPage();
      currentY = 20;
    }
  };

  // Record page numbers for TOC
  for (let i = 0; i < sections.length; i++) {
    const sec = sections[i]!;
    const entry = sectionEntries[i];
    if (entry) {
      entry.pageNumber = (doc.internal as unknown as { getCurrentPageInfo: () => { pageNumber: number } }).getCurrentPageInfo().pageNumber;
    }
    renderSection(sec.ordinal, sec.description, sec.children, sec.subtotal);
  }

  // Ungrouped positions (if any)
  if (ungrouped.length > 0) {
    const ungroupedSubtotal = ungrouped.reduce((sum, p) => sum + positionTotalForPdf(p, fxOpts), 0);
    renderSection('', L.ungrouped, ungrouped, ungroupedSubtotal);
  }
}

/* ── Summary page ───────────────────────────────────────────────────────── */

function renderSummary(
  doc: jsPDF,
  options: PdfReportOptions,
  locale: string,
): void {
  doc.addPage();
  const pageW = doc.internal.pageSize.getWidth();
  const L = reportLabels(locale);

  // Heading
  doc.setFillColor(...BRAND_DARK);
  doc.rect(0, 0, pageW, 18, 'F');
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(13);
  doc.setTextColor(...WHITE);
  doc.text(L.summaryTitle, 20, 12);

  // Section subtotals table
  const fxOpts: PdfFxOpts = { baseCurrency: options.baseCurrency, fxRates: options.fxRates };
  const { sections, ungrouped } = buildSectionGroups(options.positions, fxOpts);
  const sectionRows = sections.map((s) => [
    `${s.ordinal}  ${s.description}`.trim(),
    formatCurrency(s.subtotal, options.currency, locale),
  ]);
  if (ungrouped.length > 0) {
    const ungroupedTotal = ungrouped.reduce((sum, p) => sum + positionTotalForPdf(p, fxOpts), 0);
    sectionRows.push([L.ungrouped, formatCurrency(ungroupedTotal, options.currency, locale)]);
  }

  if (sectionRows.length > 0) {
    autoTable(doc, {
      startY: 24,
      head: [[L.section, L.subtotal]],
      body: sectionRows,
      headStyles: { fillColor: BRAND_MID, textColor: WHITE, fontSize: 8.5 },
      bodyStyles: { fontSize: 8.5, textColor: BRAND_DARK },
      alternateRowStyles: { fillColor: [248, 250, 252] as [number, number, number] },
      columnStyles: {
        0: { cellWidth: 'auto' },
        1: { cellWidth: 40, halign: 'right' },
      },
      margin: { left: 15, right: 15 },
      theme: 'grid',
      tableLineColor: BRAND_LIGHT,
      tableLineWidth: 0.2,
    });
  }

  const afterSectionsY = (doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable?.finalY ?? 24;

  // Financial summary table
  const summaryRows: [string, string][] = [
    [L.directCost, formatCurrency(options.directCost, options.currency, locale)],
  ];

  for (const m of options.markupTotals) {
    summaryRows.push([
      `${m.name} (${m.percentage}%)`,
      formatCurrency(m.amount, options.currency, locale),
    ]);
  }

  const vatLabel = `${L.vat} (${(options.vatRate * 100).toFixed(0)}%)`;

  autoTable(doc, {
    startY: afterSectionsY + 10,
    head: [[L.item, L.amount]],
    body: [
      ...summaryRows,
      [L.netTotal, formatCurrency(options.netTotal, options.currency, locale)],
      [vatLabel, formatCurrency(options.vatAmount, options.currency, locale)],
    ],
    headStyles: { fillColor: BRAND_MID, textColor: WHITE, fontSize: 8.5 },
    bodyStyles: { fontSize: 8.5, textColor: BRAND_DARK },
    alternateRowStyles: { fillColor: [248, 250, 252] as [number, number, number] },
    columnStyles: {
      0: { cellWidth: 'auto' },
      1: { cellWidth: 40, halign: 'right' },
    },
    margin: { left: 15, right: 15 },
    theme: 'grid',
    tableLineColor: BRAND_LIGHT,
    tableLineWidth: 0.2,
  });

  const afterSummaryY = (doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable?.finalY ?? afterSectionsY + 10;

  // Gross total highlight box
  const boxY = afterSummaryY + 8;
  doc.setFillColor(...BRAND_DARK);
  doc.roundedRect(15, boxY, pageW - 30, 16, 3, 3, 'F');

  doc.setFont('helvetica', 'bold');
  doc.setFontSize(11);
  doc.setTextColor(...WHITE);
  doc.text(L.grossTotal.toUpperCase(), 22, boxY + 10);
  doc.text(formatCurrency(options.grossTotal, options.currency, locale), pageW - 22, boxY + 10, { align: 'right' });
}

/* ── Main export function ───────────────────────────────────────────────── */

/**
 * Generates a professional A4 PDF report for a BOQ and triggers a browser
 * download. The report includes:
 *  - Cover page with project name, BOQ title, date, and key metrics
 *  - Table of Contents (when there are multiple sections)
 *  - BOQ tables grouped by section with subtotals
 *  - Cost summary: Direct Cost, Markups (itemised), Net Total, VAT, Gross Total
 *  - Page footers with "Page X of Y"
 */
export function generateBOQPdf(options: PdfReportOptions): void {
  const locale = options.locale ?? 'en-US';

  const doc = new jsPDF({
    orientation: 'portrait',
    unit: 'mm',
    format: 'a4',
  });

  // PDF metadata — embedded identity markers
  const docLabels = reportLabels(locale);
  doc.setProperties({
    title: options.projectName || docLabels.title,
    subject: docLabels.title,
    author: 'Neoconstruction',
    creator: 'Neoconstruction',
    keywords: 'Devis, Neoconstruction',
  });

  // ── 1. Cover page ──────────────────────────────────────────────────────
  renderCoverPage(doc, options, locale);

  // ── 2. Prepare section entries for TOC ────────────────────────────────
  const { sections } = buildSectionGroups(options.positions, {
    baseCurrency: options.baseCurrency,
    fxRates: options.fxRates,
  });
  const sectionEntries: SectionEntry[] = sections.map((s) => ({
    ordinal: s.ordinal,
    description: s.description,
    subtotal: s.subtotal,
    pageNumber: 0,
  }));

  // ── 3. Table of Contents (only if there are multiple sections) ─────────
  const hasTOC = sections.length > 1;
  if (hasTOC) {
    doc.addPage();
    // TOC is rendered with placeholder page numbers first; we re-render
    // it after the BOQ tables to fill in correct page references.
    renderTableOfContents(doc, sectionEntries);
  }

  // ── 4. BOQ tables ──────────────────────────────────────────────────────
  doc.addPage();
  renderBOQTables(doc, options, locale, sectionEntries);

  // ── 5. Re-render TOC with actual page numbers ─────────────────────────
  if (hasTOC) {
    // TOC is on page 2 (cover is page 1)
    doc.setPage(2);
    // Clear the page by drawing white rectangle
    const pageW = doc.internal.pageSize.getWidth();
    const pageH = doc.internal.pageSize.getHeight();
    doc.setFillColor(...WHITE);
    doc.rect(0, 0, pageW, pageH, 'F');
    renderTableOfContents(doc, sectionEntries);
  }

  // ── 6. Summary page ────────────────────────────────────────────────────
  // NEOFFICE — the cost-summary page is all figures; skip it for a price-free
  // export (bordereau).
  if (options.showPrices !== false) {
    renderSummary(doc, options, locale);
  }

  // ── 7. Page footers ────────────────────────────────────────────────────
  addPageFooters(doc, options);

  // ── 8. Download ───────────────────────────────────────────────────────
  const safeName = options.boqTitle.replace(/[^a-zA-Z0-9_\- ]/g, '').trim() || 'BOQ';
  doc.save(`${safeName}.pdf`);
}
