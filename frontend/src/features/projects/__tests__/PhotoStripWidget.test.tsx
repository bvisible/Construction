// @ts-nocheck
/**
 * Tests for the project-overview Photo strip widget (#284).
 *
 * Tigercatman reported that images uploaded into Project Files never showed
 * in the Photo strip - it only read the dedicated photos table. These tests
 * pin the fix: the strip now MERGES dedicated site photos with image-type
 * general documents, sorts newest-first, and loads every thumbnail through
 * the authenticated <AuthImage> path (a bare <img src> would 401 on the
 * bearer-protected endpoints).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

// The widget reads both endpoints through the shared apiGet helper.
vi.mock('@/shared/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/shared/lib/api')>(
    '@/shared/lib/api',
  );
  return { ...actual, apiGet: vi.fn() };
});

import { apiGet } from '@/shared/lib/api';
import { PhotoStripWidget } from '../components/ProjectWidgets';

function renderWithProviders(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Route apiGet by URL so the two widget queries get distinct payloads. */
function mockApi(byUrl: Record<string, unknown>) {
  (apiGet as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
    for (const [needle, payload] of Object.entries(byUrl)) {
      if (url.includes(needle)) return Promise.resolve(payload);
    }
    return Promise.resolve([]);
  });
}

describe('PhotoStripWidget (#284 - uploaded images appear in the strip)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Thumbnails are bearer-protected; <AuthImage> fetches the bytes with the
    // token and renders an object URL. Stub the blob fetch + object-URL plumbing.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        blob: async () => new Blob(['x'], { type: 'image/jpeg' }),
      }),
    );
    if (!('createObjectURL' in URL)) {
      (URL as unknown as { createObjectURL: unknown }).createObjectURL = () => '';
      (URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = () => {};
    }
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
  });

  it('shows an image uploaded into project files even with zero dedicated photos', async () => {
    mockApi({
      '/v1/documents/photos/': [],
      '/v1/documents/?project_id=': [
        {
          id: 'doc-img-1',
          name: 'site_photo.jpg',
          mime_type: 'image/jpeg',
          created_at: '2026-06-01T10:00:00Z',
        },
        // A non-image document must be ignored.
        {
          id: 'doc-pdf-1',
          name: 'contract.pdf',
          mime_type: 'application/pdf',
          created_at: '2026-06-02T10:00:00Z',
        },
      ],
    });

    renderWithProviders(<PhotoStripWidget projectId="proj-1" />);

    // The empty state must NOT show - we have one image document.
    await waitFor(() => {
      expect(screen.queryByText(/No photos yet/i)).not.toBeInTheDocument();
    });
    // Exactly one tile rendered (the image doc), and its thumbnail was fetched
    // with auth via AuthImage (the document download endpoint).
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/documents/doc-img-1/download/',
        expect.objectContaining({ headers: expect.anything() }),
      );
    });
    // The PDF document must never be fetched as a thumbnail.
    expect(global.fetch).not.toHaveBeenCalledWith(
      '/api/v1/documents/doc-pdf-1/download/',
      expect.anything(),
    );
  });

  it('merges dedicated photos with image documents and loads both via AuthImage', async () => {
    mockApi({
      '/v1/documents/photos/': [
        { id: 'photo-1', taken_at: '2026-06-03T10:00:00Z', created_at: '2026-06-03T10:00:00Z' },
      ],
      '/v1/documents/?project_id=': [
        {
          id: 'doc-img-2',
          name: 'progress.png',
          mime_type: 'image/png',
          created_at: '2026-06-04T10:00:00Z',
        },
      ],
    });

    renderWithProviders(<PhotoStripWidget projectId="proj-1" />);

    // Photo thumb uses the dedicated thumb route...
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/documents/photos/photo-1/thumb/',
        expect.objectContaining({ headers: expect.anything() }),
      );
    });
    // ...and the image document uses its download route.
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/v1/documents/doc-img-2/download/',
      expect.objectContaining({ headers: expect.anything() }),
    );
  });

  it('shows the empty state when there are neither photos nor image documents', async () => {
    mockApi({
      '/v1/documents/photos/': [],
      '/v1/documents/?project_id=': [
        { id: 'doc-pdf-2', name: 'spec.pdf', mime_type: 'application/pdf' },
      ],
    });

    renderWithProviders(<PhotoStripWidget projectId="proj-1" />);

    await waitFor(() => {
      expect(screen.getByText(/No photos yet/i)).toBeInTheDocument();
    });
  });
});
