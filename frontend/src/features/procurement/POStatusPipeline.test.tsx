// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <POStatusPipeline>.

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { POStatusPipeline } from './POStatusPipeline';

describe('<POStatusPipeline>', () => {
  it('renders four dots for an in-flight PO', () => {
    const { container } = render(<POStatusPipeline status="issued" />);
    // 4 dot spans = 4 stages of the pipeline.
    const dots = container.querySelectorAll('span');
    expect(dots.length).toBe(4);
  });

  it('exposes an accessible label with the current stage', () => {
    render(<POStatusPipeline status="partially_received" />);
    const node = screen.getByRole('img');
    expect(node).toHaveAttribute('aria-label', expect.stringContaining('Partial'));
  });

  it('falls back to draft for an unknown status', () => {
    render(<POStatusPipeline status="bogus" />);
    const node = screen.getByRole('img');
    expect(node).toHaveAttribute('aria-label', expect.stringContaining('Draft'));
  });

  it('collapses to a single bar when cancelled', () => {
    const { container } = render(<POStatusPipeline status="cancelled" />);
    const dots = container.querySelectorAll('span');
    expect(dots.length).toBe(1);
    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      expect.stringContaining('Cancelled'),
    );
  });

  it('marks the completed stage as the last active dot', () => {
    render(<POStatusPipeline status="completed" />);
    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      expect.stringContaining('Completed'),
    );
  });
});
