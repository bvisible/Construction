/**
 * Unit conversion utility for metric ↔ imperial.
 *
 * Used by QuantityDisplay to auto-convert values when the user
 * preference differs from the source measurement system.
 */

export interface ConversionResult {
  value: number;
  unit: string;
  displayUnit: string;
}

interface ConversionEntry {
  factor: number;
  unit: string;
  display: string;
}

const METRIC_TO_IMPERIAL: Record<string, ConversionEntry> = {
  m: { factor: 3.2808399, unit: 'ft', display: 'ft' },
  m2: { factor: 10.7639, unit: 'ft2', display: 'sq ft' },
  m3: { factor: 35.3147, unit: 'ft3', display: 'cu ft' },
  // Superscript variants of the area / volume codes used on the takeoff
  // canvas + ledger ("m²" / "m³"). Mapped to superscript imperial
  // labels so the converted display stays in the same visual style as the
  // metric source rather than switching to the "sq ft" / "cu ft" spelling.
  'm²': { factor: 10.7639, unit: 'ft2', display: 'ft²' },
  'm³': { factor: 35.3147, unit: 'ft3', display: 'ft³' },
  kg: { factor: 2.20462, unit: 'lb', display: 'lb' },
  km: { factor: 0.621371, unit: 'mi', display: 'mi' },
  cm: { factor: 0.393701, unit: 'in', display: 'in' },
  mm: { factor: 0.0393701, unit: 'in', display: 'in' },
  t: { factor: 1.10231, unit: 'ton', display: 'ton' },
  lm: { factor: 3.28084, unit: 'lft', display: 'l.ft' },
  // Extended BoQ area / land / liquid coverage. Small areas relabel to
  // square inches, decimetre-squared to square feet, hectares to acres and
  // litres to US gallons. Superscript variants mirror the m2/m3 handling
  // above so a "cm²" stored on the takeoff layer converts the same as "cm2".
  mm2: { factor: 0.0015500031, unit: 'in2', display: 'sq in' },
  cm2: { factor: 0.15500031, unit: 'in2', display: 'sq in' },
  dm2: { factor: 0.107639104, unit: 'ft2', display: 'sq ft' },
  'mm²': { factor: 0.0015500031, unit: 'in2', display: 'in²' },
  'cm²': { factor: 0.15500031, unit: 'in2', display: 'in²' },
  'dm²': { factor: 0.107639104, unit: 'ft2', display: 'ft²' },
  ha: { factor: 2.4710538, unit: 'ac', display: 'ac' },
  l: { factor: 0.264172052, unit: 'gal', display: 'gal' },
};

const IMPERIAL_TO_METRIC: Record<string, ConversionEntry> = {
  ft: { factor: 0.3048, unit: 'm', display: 'm' },
  ft2: { factor: 0.092903, unit: 'm2', display: 'm\u00B2' },
  ft3: { factor: 0.0283168, unit: 'm3', display: 'm\u00B3' },
  lb: { factor: 0.453592, unit: 'kg', display: 'kg' },
  mi: { factor: 1.60934, unit: 'km', display: 'km' },
  in: { factor: 25.4, unit: 'mm', display: 'mm' },
  ton: { factor: 0.907185, unit: 't', display: 't' },
  lft: { factor: 0.3048, unit: 'lm', display: 'l.m' },
  'sq ft': { factor: 0.092903, unit: 'm2', display: 'm\u00B2' },
  'cu ft': { factor: 0.0283168, unit: 'm3', display: 'm\u00B3' },
  ac: { factor: 0.404685642, unit: 'ha', display: 'ha' },
  gal: { factor: 3.785411784, unit: 'l', display: 'l' },
};

/** Display-friendly labels for common metric units. */
const METRIC_DISPLAY: Record<string, string> = {
  m: 'm',
  m2: 'm\u00B2',
  m3: 'm\u00B3',
  // Already-superscript inputs map to themselves so they are recognised as
  // metric (the takeoff layer stores units as "m\u00B2" / "m\u00B3", not "m2" / "m3").
  'm\u00B2': 'm\u00B2',
  'm\u00B3': 'm\u00B3',
  kg: 'kg',
  km: 'km',
  cm: 'cm',
  mm: 'mm',
  t: 't',
  lm: 'l.m',
  mm2: 'mm²',
  cm2: 'cm²',
  dm2: 'dm²',
  'mm²': 'mm²',
  'cm²': 'cm²',
  'dm²': 'dm²',
  ha: 'ha',
  l: 'l',
};

/** Display-friendly labels for common imperial units. */
const IMPERIAL_DISPLAY: Record<string, string> = {
  ft: 'ft',
  ft2: 'sq ft',
  ft3: 'cu ft',
  lb: 'lb',
  mi: 'mi',
  in: 'in',
  in2: 'sq in',
  ton: 'ton',
  lft: 'l.ft',
  ac: 'ac',
  gal: 'gal',
};

/**
 * Returns the human-friendly display string for a unit code.
 * Falls back to the raw unit code when no mapping is available.
 */
export function getDisplayUnit(unit: string): string {
  return METRIC_DISPLAY[unit] ?? IMPERIAL_DISPLAY[unit] ?? unit;
}

/**
 * Detect whether a unit belongs to the metric system.
 * Returns `true` for metric units, `false` for imperial, `null` for unknowns.
 */
export function isMetricUnit(unit: string): boolean | null {
  if (unit in METRIC_TO_IMPERIAL || unit in METRIC_DISPLAY) return true;
  if (unit in IMPERIAL_TO_METRIC || unit in IMPERIAL_DISPLAY) return false;
  return null;
}

/**
 * Convert a value from its source unit to the target measurement system.
 *
 * If the unit is already in the target system, or no conversion exists,
 * the value is returned unchanged with a display-friendly unit label.
 */
export function convertUnit(
  value: number,
  fromUnit: string,
  toSystem: 'metric' | 'imperial',
): ConversionResult {
  const unitLower = fromUnit.toLowerCase().trim();
  const unitKey = fromUnit.trim();

  // Target is imperial — convert from metric
  if (toSystem === 'imperial') {
    const entry = METRIC_TO_IMPERIAL[unitKey] ?? METRIC_TO_IMPERIAL[unitLower];
    if (entry) {
      return {
        value: value * entry.factor,
        unit: entry.unit,
        displayUnit: entry.display,
      };
    }
  }

  // Target is metric — convert from imperial
  if (toSystem === 'metric') {
    const entry = IMPERIAL_TO_METRIC[unitKey] ?? IMPERIAL_TO_METRIC[unitLower];
    if (entry) {
      return {
        value: value * entry.factor,
        unit: entry.unit,
        displayUnit: entry.display,
      };
    }
  }

  // No conversion available — return as-is with display label
  return {
    value,
    unit: fromUnit,
    displayUnit: getDisplayUnit(fromUnit),
  };
}

/** A quantity ready for display: numeric value + the label to show beside it. */
export interface DisplayQuantity {
  value: number;
  unit: string;
}

/**
 * Convert a metric-canonical quantity into the user's measurement system,
 * the single decision every display / export surface should funnel through.
 *
 * The whole app stores quantities metric-canonical (m / m2 / m3 / kg ...).
 * This helper takes such a value plus the target `system` and returns what
 * to render:
 *   - `metric`   : the value passes through bit-for-bit; only the unit label
 *                  is normalised to its display form ("m2" -> "m²"), so a
 *                  metric user sees byte-identical output to before.
 *   - `imperial` : the value is scaled and the unit relabelled
 *                  (m -> ft, m² -> ft², m³ -> ft³, kg -> lb ...).
 * Units with no imperial mapping (pcs, lsum, hr, %) pass through unchanged
 * in both systems, which is the correct behaviour for countable / lump /
 * dimensionless items.
 *
 * Storage is never touched — callers feed the canonical metric value in and
 * use the returned pair purely for rendering or human-readable export.
 */
export function toDisplayQuantity(
  value: number,
  metricUnit: string,
  system: 'metric' | 'imperial',
): DisplayQuantity {
  if (system !== 'imperial') {
    return { value, unit: getDisplayUnit(metricUnit) };
  }
  const result = convertUnit(value, metricUnit, 'imperial');
  return { value: result.value, unit: result.displayUnit };
}

/**
 * The display unit label a metric unit resolves to in the target system,
 * without needing a value. Used where only a unit column / suffix is
 * rendered (a header, an input adornment, a standalone unit cell).
 */
export function displayUnitFor(
  metricUnit: string,
  system: 'metric' | 'imperial',
): string {
  return toDisplayQuantity(0, metricUnit, system).unit;
}

/**
 * Reverse of {@link toDisplayQuantity} for an editable field: take a number a
 * user typed *in the displayed system* and return the metric-canonical value
 * to store. For `metric` the value is returned unchanged; for `imperial` it
 * is divided back out (107.64 ft² -> 10 m²). Units with no mapping pass
 * through. This is what an imperial-aware grid's value-parser must call so a
 * user editing a converted cell never overwrites canonical metric storage
 * with the imperial number they see.
 */
export function fromDisplayQuantity(
  value: number,
  metricUnit: string,
  system: 'metric' | 'imperial',
): number {
  if (system !== 'imperial') return value;
  const entry =
    METRIC_TO_IMPERIAL[metricUnit.trim()] ??
    METRIC_TO_IMPERIAL[metricUnit.toLowerCase().trim()];
  if (!entry || !entry.factor) return value;
  return value / entry.factor;
}

/**
 * The scalar a metric unit scales by in the target system: the number `f`
 * such that `displayValue = metricValue * f`. Returns `1` for the metric
 * system and for any unit with no imperial mapping, so callers can multiply
 * or divide unconditionally. This is the single source of the reciprocal used
 * to re-express a per-unit rate against a converted quantity.
 */
export function conversionFactorFor(
  metricUnit: string,
  system: 'metric' | 'imperial',
): number {
  if (system !== 'imperial') return 1;
  const entry =
    METRIC_TO_IMPERIAL[metricUnit.trim()] ??
    METRIC_TO_IMPERIAL[metricUnit.toLowerCase().trim()];
  return entry && entry.factor ? entry.factor : 1;
}

/**
 * Re-express a per-unit rate so it pairs with a quantity shown in `system`.
 *
 * A rate is money per ONE metric unit (50 currency / m). When the paired
 * quantity is displayed converted (2.31 m -> 7.58 ft) the rate has to be shown
 * against the SAME displayed unit or the line stops reconciling: 7.58 ft is
 * priced at 50 / 3.28084 = 15.24 / ft so that qty * rate still equals the
 * (invariant) line total. The money total never changes - only the per-unit
 * basis is restated. Units with no mapping return the rate unchanged.
 */
export function toDisplayRate(
  rate: number,
  metricUnit: string,
  system: 'metric' | 'imperial',
): number {
  const factor = conversionFactorFor(metricUnit, system);
  return factor ? rate / factor : rate;
}

/**
 * Reverse of {@link toDisplayRate}: take a rate a user typed against a
 * displayed (imperial) unit and return the metric-canonical rate to store
 * (15.24 / ft -> 50 / m). Storage stays metric so re-import and the canonical
 * exports are unaffected. Units with no mapping pass through unchanged.
 */
export function fromDisplayRate(
  rate: number,
  metricUnit: string,
  system: 'metric' | 'imperial',
): number {
  return rate * conversionFactorFor(metricUnit, system);
}
