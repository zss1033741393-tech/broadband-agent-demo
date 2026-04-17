import type { RenderBlock } from './render';

export interface ThinkingEvent {
  delta: string;
  /** 存在时表示这段 thinking 属于某个 step，否则属于 Orchestrator */
  stepId?: string;
}
export interface TextEvent {
  delta: string;
}
export interface StepStartEvent {
  stepId: string;
  title: string;
}
export interface SubStepEvent {
  stepId: string;
  subStepId: string;
  name: string;
  scriptPath?: string;
  callArgs?: string[];
  stdout?: string;
  stderr?: string;
  completedAt: string;
  durationMs: number;
}
export interface StepEndEvent {
  stepId: string;
}
export type RenderEvent = RenderBlock;
export interface DoneEvent {
  messageId: string;
  thinkingDurationSec: number;
}
export interface ErrorEvent {
  message: string;
}
export interface ReportEvent {
  renderType: 'insight';
  renderData: {
    charts: import('./render').ChartItem[];
    markdownReport: string;
  };
}

export interface WifiImage {
  imageId: string;
  imageUrl: string;
  title: string;
  kind: string;
}

export interface WifiResultEvent {
  renderType: 'wifi_simulation';
  renderData: {
    preset: string;
    gridSize: number;
    apCount: number;
    targetApCount: number;
    summary: string;
    stats: Record<string, unknown>;
    images: WifiImage[];
    dataFiles: unknown[];
  };
}

export interface ExperienceAssuranceResultEvent {
  renderType: 'experience_assurance';
  renderData: {
    businessType: string;
    applicationType: string;
    application: string;
    isMock: boolean;
    taskData: Record<string, unknown>;
  };
}

export type SseEventName =
  | 'thinking'
  | 'text'
  | 'step_start'
  | 'sub_step'
  | 'step_end'
  | 'render'
  | 'wifi_result'
  | 'report'
  | 'experience_assurance_result'
  | 'done'
  | 'error';
