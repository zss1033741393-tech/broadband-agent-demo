import type { RenderBlock } from './render';
import type { InsightState } from './insight';

export interface SubStep {
  subStepId: string;
  name: string;
  scriptPath?: string;
  callArgs?: string[];
  stdout?: string;
  stderr?: string;
  completedAt: string;
  durationMs: number;
}

/** step 内部有序渲染项：thinking、sub_step、text 按实际到达顺序穿插 */
export type StepItem =
  | {
      type: 'thinking';
      content: string;
      startedAt: number;   // Date.now()，前端打点
      endedAt?: number;    // 下一个 sub_step 或 step_end 到达时关闭
    }
  | { type: 'sub_step'; data: SubStep }
  | { type: 'text'; content: string };

export interface Step {
  stepId: string;
  title: string;
  /** 有序渲染项，thinking 与 sub_step 穿插 */
  items: StepItem[];
  /** 仅用于显示步骤数量和历史重建 */
  subSteps: SubStep[];
  /** step_end 事件到达后标记为 true */
  completed?: boolean;
}

export type MessageRole = 'user' | 'assistant';

/**
 * 有序渲染块：SSE 事件流中各类内容按到达顺序追加到 blocks[]，
 * 渲染时直接遍历，保证 thinking / step / text 的视觉顺序与流顺序一致。
 */
export type MessageBlock =
  | { type: 'thinking'; content: string; startedAt: number; endedAt?: number }
  | { type: 'step'; stepId: string }
  | { type: 'text'; content: string };

export interface Message {
  id: string;
  conversationId: string;
  role: MessageRole;
  content: string;
  thinkingContent?: string;
  thinkingDurationSec?: number;
  steps?: Step[];
  renderBlocks?: RenderBlock[];
  /** 流式渲染块（按实际到达顺序）；历史消息按 thinking→steps→text 重建 */
  blocks?: MessageBlock[];
  /** 流式过程标记：true 表示该 message 还在生成中 */
  streaming?: boolean;
  /** 错误标记：流式过程中报错 */
  error?: string;
  /** InsightAgent 阶段进度（从 text 流事件中解析） */
  insightState?: InsightState;
  createdAt: string;
}

export interface MessageListResp {
  list: Message[];
}
