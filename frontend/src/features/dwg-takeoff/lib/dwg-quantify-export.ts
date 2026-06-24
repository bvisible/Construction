/**
 * Client-side Excel export for the DWG auto-quantify table.
 *
 * Turns the per-layer vector quantities (and the count-by-block rollup) into
 * a downloadable .xlsx so estimators can hand the takeoff straight to a
 * spreadsheet without retyping. exceljs is imported lazily (≈1 MB) so it
 * never weighs down the main bundle - only when the user clicks Export.
 *
 * Mirrors the established pattern in ``features/takeoff/lib/takeoff-export.ts``
 * (lazy ctor resolve + ``neutraliseFormula`` defence + blob download).
 */

import type * as ExcelJS from 'exceljs';
import type { LayerQuantity } from './auto-quantify';

const HEADER_FILL = 'FF1F2937';

/**
 * Defuse spreadsheet-formula injection: any cell text starting with a
 * formula trigger (``= + - @`` or a control char) is prefixed with an
 * apostrophe so Excel/Sheets treats it as literal text. Mirrors the backend
 * and BOQ-export guards (OWASP CSV-injection defence).
 */
export function neutraliseFormula(value: string): string {
  if (value && /^[=+\-@\t\r\n]/.test(value)) return `'${value}`;
  return value;
}

/** Standard blob → ``<a download>`` trigger with deferred URL revoke. */
export function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export interface QuantifyExportContext {
  /** Drawing name, used for the sheet header + filename. */
  drawingName: string;
  /** Per-layer auto-quantify rows (from ``quantifyByLayer``). */
  layerQuantities: LayerQuantity[];
  /** Count-by-block rollup (INSERT entities), optional. */
  byBlock?: { name: string; count: number }[];
  /** Manual count-tool tally, optional. */
  countTotal?: number;
  /** Override-able for deterministic tests. */
  exportDate?: Date;
}

function styleHeader(row: ExcelJS.Row): void {
  row.font = { bold: true, color: { argb: 'FFFFFFFF' } };
  row.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: HEADER_FILL } };
  row.alignment = { vertical: 'middle' };
}

/**
 * Build a workbook with a "Quantities by layer" sheet (+ a "Count by block"
 * sheet when the drawing has block references).
 */
export async function buildQuantifyWorkbook(
  ctx: QuantifyExportContext,
): Promise<ExcelJS.Workbook> {
  const mod = await import('exceljs');
  const Ctor = (mod.Workbook ?? mod.default.Workbook) as typeof ExcelJS.Workbook;
  const wb = new Ctor();
  wb.creator = 'OpenConstructionERP';
  wb.created = ctx.exportDate ?? new Date();

  /* ── Quantities by layer ─────────────────────────────────────── */
  const ws = wb.addWorksheet('Quantities by layer');
  ws.columns = [
    { header: 'Layer', key: 'layer', width: 26 },
    { header: 'Measure', key: 'measure', width: 12 },
    { header: 'Quantity', key: 'quantity', width: 14 },
    { header: 'Unit', key: 'unit', width: 8 },
    { header: 'Area (m²)', key: 'area', width: 12 },
    { header: 'Length (m)', key: 'length', width: 12 },
    { header: 'Entities', key: 'entities', width: 10 },
  ];
  styleHeader(ws.getRow(1));

  let totalArea = 0;
  let totalLength = 0;
  let totalEntities = 0;
  for (const row of ctx.layerQuantities) {
    totalArea += row.area;
    totalLength += row.length;
    totalEntities += row.count;
    ws.addRow({
      layer: neutraliseFormula(row.layer),
      measure: row.primary,
      quantity: Math.round(row.quantity * 1000) / 1000,
      unit: row.unit,
      area: row.area > 0 ? Math.round(row.area * 1000) / 1000 : '',
      length: row.length > 0 ? Math.round(row.length * 1000) / 1000 : '',
      entities: row.count,
    });
  }

  const totalRow = ws.addRow({
    layer: 'TOTAL',
    measure: '',
    quantity: '',
    unit: '',
    area: Math.round(totalArea * 100) / 100,
    length: Math.round(totalLength * 100) / 100,
    entities: totalEntities,
  });
  totalRow.font = { bold: true };
  totalRow.border = { top: { style: 'thin' } };

  if (ctx.countTotal && ctx.countTotal > 0) {
    const cRow = ws.addRow({ layer: 'Manual count items', measure: '', quantity: ctx.countTotal, unit: 'nr' });
    cRow.font = { italic: true };
  }

  /* ── Count by block ──────────────────────────────────────────── */
  if (ctx.byBlock && ctx.byBlock.length > 0) {
    const wsB = wb.addWorksheet('Count by block');
    wsB.columns = [
      { header: 'Block', key: 'block', width: 30 },
      { header: 'Count', key: 'count', width: 10 },
    ];
    styleHeader(wsB.getRow(1));
    let total = 0;
    for (const b of ctx.byBlock) {
      total += b.count;
      wsB.addRow({ block: neutraliseFormula(b.name), count: b.count });
    }
    const tRow = wsB.addRow({ block: 'TOTAL', count: total });
    tRow.font = { bold: true };
    tRow.border = { top: { style: 'thin' } };
  }

  return wb;
}

/** Build + download the quantify workbook as ``dwg-quantities-<name>.xlsx``. */
export async function exportQuantifyToExcel(ctx: QuantifyExportContext): Promise<void> {
  const wb = await buildQuantifyWorkbook(ctx);
  const buf = await wb.xlsx.writeBuffer();
  const blob = new Blob([buf], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
  const slug =
    (ctx.drawingName || 'drawing')
      .replace(/[^\p{L}\p{N}]+/gu, '_')
      .replace(/_+/g, '_')
      .replace(/^_|_$/g, '')
      .toLowerCase() || 'drawing';
  triggerDownload(blob, `dwg-quantities-${slug}.xlsx`);
}
