export type PhaseStatus = 'pending' | 'running' | 'done' | 'reflected';
export type StepStatus = 'pending' | 'running' | 'done';

export interface InsightStep {
  stepId: number;
  stepName?: string;
  insightTypes: string[];
  rationale: string;
  status: StepStatus;
  summary?: string;
  significance?: number;
}

export interface InsightPhase {
  phaseId: number;
  name: string;
  milestone: string;
  description: string;
  status: PhaseStatus;
  steps: InsightStep[];
  reflection?: { choice: string; reason: string };
}

export interface InsightState {
  goal: string;
  totalPhases: number;
  phases: InsightPhase[];
}

/** 从 text 流中解析出的结构化事件 */
export type InsightEvent =
  | { type: 'plan'; goal: string; totalPhases: number; phases: Omit<InsightPhase, 'status' | 'steps' | 'reflection'>[] }
  | { type: 'decompose_result'; phaseId: number; steps: InsightStep[] }
  | { type: 'phase_start'; phaseId: number }
  | { type: 'step_result'; phaseId: number; stepId: number; summary: string; significance: number; status: string }
  | { type: 'phase_complete'; phaseId: number; steps: { stepId: number; status: string; summary: string; significance: number }[] }
  | { type: 'reflect'; phaseId: number; choice: string; reason: string };
