// AI Agents — typed client for the /api/v1/ai-agents/* surface.

import { apiDelete, apiGet, apiPost, apiPut } from '@/shared/lib/api';

export interface AgentDescriptor {
  name: string;
  description: string;
  system_prompt?: string;
  max_iterations: number;
  allowed_tools: string[];
  // Presentation metadata (see backend base.Agent).
  display_name?: string;
  category?: string;
  icon?: string;
  tagline?: string;
  example_prompts?: string[];
  // True for the caller's own user-authored agents (editable/deletable).
  is_custom?: boolean;
  custom_id?: string | null;
}

// The friendly guided-builder spec a non-technical user fills in. The backend
// compiles these plain-language fields into a well-formed system prompt.
export interface GuidedAgentSpec {
  role?: string;
  goal: string;
  audience?: string;
  output_format?: string;
  extra_guidance?: string;
}

export interface CustomAgent {
  id: string;
  user_id: string;
  display_name: string;
  tagline: string;
  description: string;
  category: string;
  icon: string;
  example_prompts: string[];
  system_prompt: string;
  guided: GuidedAgentSpec | null;
  created_at: string;
  updated_at: string;
}

export interface CustomAgentInput {
  display_name: string;
  tagline?: string;
  description?: string;
  category: string;
  icon: string;
  example_prompts?: string[];
  guided?: GuidedAgentSpec | null;
  system_prompt?: string;
}

export type AgentStepRole =
  | 'thought'
  | 'tool_call'
  | 'observation'
  | 'answer'
  | 'error';

export interface AgentStep {
  id: string;
  step_idx: number;
  role: AgentStepRole;
  content: unknown;
  token_count: number;
  created_at: string;
}

export interface AgentRun {
  id: string;
  agent_name: string;
  project_id: string | null;
  user_id: string;
  status: 'running' | 'completed' | 'failed';
  failure_reason: string | null;
  user_input: string;
  final_output: string | null;
  iterations: number;
  total_tokens: number;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
  steps: AgentStep[];
}

export interface AgentRunListItem {
  id: string;
  agent_name: string;
  project_id: string | null;
  user_id: string;
  status: 'running' | 'completed' | 'failed';
  failure_reason: string | null;
  iterations: number;
  total_tokens: number;
  created_at: string;
  updated_at: string;
}

export interface CreateAgentRunRequest {
  agent_name: string;
  project_id?: string | null;
  user_input: string;
}

export interface AgentHealth {
  llm_configured: boolean;
  provider: string | null;
  model: string | null;
  settings_url: string;
}

export const aiAgentsApi = {
  listAgents: () => apiGet<AgentDescriptor[]>('/v1/ai-agents/agents/'),
  listRuns: (projectId?: string) =>
    apiGet<AgentRunListItem[]>(
      `/v1/ai-agents/runs/${projectId ? `?project_id=${projectId}` : ''}`,
    ),
  getRun: (runId: string) => apiGet<AgentRun>(`/v1/ai-agents/runs/${runId}`),
  startRun: (body: CreateAgentRunRequest) =>
    apiPost<AgentRun, CreateAgentRunRequest>('/v1/ai-agents/runs/', body),
  health: () => apiGet<AgentHealth>('/v1/ai-agents/health/'),

  // Custom (user-authored) agents.
  listCustomAgents: () => apiGet<CustomAgent[]>('/v1/ai-agents/custom/'),
  createCustomAgent: (body: CustomAgentInput) =>
    apiPost<CustomAgent, CustomAgentInput>('/v1/ai-agents/custom/', body),
  updateCustomAgent: (id: string, body: CustomAgentInput) =>
    apiPut<CustomAgent, CustomAgentInput>(`/v1/ai-agents/custom/${id}`, body),
  deleteCustomAgent: (id: string) => apiDelete(`/v1/ai-agents/custom/${id}`),
};
