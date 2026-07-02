// //// NEOFFICE — verifies formula-typed variables (reusable named calculations).
import { describe, it, expect } from 'vitest';
import { buildFormulaContext, evaluateFormula, type FormulaVariable } from './engine';

function ctxWith(vars: Record<string, FormulaVariable>) {
  const variables = new Map<string, FormulaVariable>();
  for (const [k, v] of Object.entries(vars)) variables.set(k, v);
  return buildFormulaContext({ positions: [], variables });
}

describe('formula-typed variables (NEOFFICE)', () => {
  it('resolves a formula variable referencing a number variable', () => {
    const ctx = ctxWith({
      GAZON: { type: 'number', value: 12 },
      EMPRISE: { type: 'formula', value: '=$GAZON * 2' },
    });
    expect(evaluateFormula('=$EMPRISE', ctx)).toBe(24);
  });

  it('composes a formula variable with other references', () => {
    const ctx = ctxWith({
      GAZON: { type: 'number', value: 12 },
      PLACE: { type: 'number', value: 15 },
      EMPRISE: { type: 'formula', value: '=$GAZON * 2' },
    });
    expect(evaluateFormula('=$EMPRISE + $PLACE', ctx)).toBe(39);
  });

  it('resolves a formula variable that references another formula variable', () => {
    const ctx = ctxWith({
      GAZON: { type: 'number', value: 12 },
      BASE: { type: 'formula', value: '=$GAZON' },
      DERIVED: { type: 'formula', value: '=$BASE * 3' },
    });
    expect(evaluateFormula('=$DERIVED', ctx)).toBe(36);
  });

  it('breaks a reference cycle instead of looping forever', () => {
    const ctx = ctxWith({
      A: { type: 'formula', value: '=$B' },
      B: { type: 'formula', value: '=$A' },
    });
    // The cycle guard throws; evaluateFormula catches it → null (no hang).
    expect(evaluateFormula('=$A', ctx)).toBeNull();
  });
});
