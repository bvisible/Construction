import { describe, it, expect } from 'vitest';
import { isProjectFilterActive } from '../ProjectsPage';

/**
 * Regression lock for #284: the filter toolbar (incl. the Active/Archived
 * switch) must stay mounted whenever a filter/search is active, even if the
 * filtered fetch returns an empty list. The page gates the toolbar on
 * `(projects.length > 0) || hasActiveFilter`, where `hasActiveFilter` is this
 * helper. Previously an empty Archived view (filter active, zero results)
 * collapsed the toolbar and stranded the user with no way back to Active.
 *
 * Testing the predicate directly keeps this lock fast and free of the page's
 * heavy map/query dependencies while still pinning the exact behaviour that
 * regressed.
 */
describe('isProjectFilterActive (#284 toolbar visibility)', () => {
  it('is false for the default view (no search, status=all, region=all)', () => {
    expect(isProjectFilterActive('', 'all', 'all')).toBe(false);
  });

  it('is true in the Archived view so the toolbar survives an empty result', () => {
    // This is the exact regression: archived view with zero archived
    // projects must still report an active filter so the toolbar (and its
    // Active/Archived switch) stays visible.
    expect(isProjectFilterActive('', 'archived', 'all')).toBe(true);
  });

  it('is true for the Active filter', () => {
    expect(isProjectFilterActive('', 'active', 'all')).toBe(true);
  });

  it('is true when a search term is present', () => {
    expect(isProjectFilterActive('tower', 'all', 'all')).toBe(true);
  });

  it('is true when a region filter is set', () => {
    expect(isProjectFilterActive('', 'all', 'Bavaria')).toBe(true);
  });
});
