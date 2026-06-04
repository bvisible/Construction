import { apiGet } from '@/shared/lib/api';

export interface PortfolioBucket {
  index: number;
  start: string;
  end: string;
  label: string;
}

export interface PortfolioCellProject {
  project_id: string | null;
  project_name: string;
  allocation_percent: number;
}

export interface PortfolioCell {
  bucket_index: number;
  allocation_percent: number;
  over_allocated: boolean;
  cross_project: boolean;
  projects: PortfolioCellProject[];
}

export interface PortfolioResourceRow {
  resource_id: string;
  code: string;
  name: string;
  resource_type: string;
  is_floating: boolean;
  peak_allocation_percent: number;
  has_conflict: boolean;
  cells: PortfolioCell[];
}

export interface PortfolioCapacityResponse {
  start: string;
  end: string;
  bucket: string;
  buckets: PortfolioBucket[];
  resources: PortfolioResourceRow[];
  total_resources: number;
  floating_resources: number;
  conflict_resources: number;
}

export const portfolioApi = {
  /** Org-wide resource utilization heatmap across every project. */
  getCapacity: (params: { start: string; end: string; bucket: 'week' | 'month' }) =>
    apiGet<PortfolioCapacityResponse>(
      `/v1/resources/portfolio/capacity?start=${encodeURIComponent(params.start)}` +
        `&end=${encodeURIComponent(params.end)}&bucket=${params.bucket}`,
    ),
};
