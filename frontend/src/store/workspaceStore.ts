import { create } from 'zustand';
import { getMessages, sendMessageStream } from '@/api/messages';

import { useConversationStore } from '@/store/conversationStore';
import { parseSseStream } from '@/utils/sseParser';
import type { Message, Step, SubStep, MessageBlock } from '@/types/message';
import type { RenderBlock, ChartItem } from '@/types/render';
import { InsightEventParser, applyInsightEvent } from '@/utils/insightEventParser';
import type {
  DoneEvent,
  ErrorEvent as SseErrorEvent,
  ReportEvent,
  WifiResultEvent,
  ExperienceAssuranceResultEvent,
  StepStartEvent,
  StepEndEvent,
  SubStepEvent,
  TextEvent,
  ThinkingEvent,
} from '@/types/sse';

// 加载类工具（读取 SKILL.md / references），实时流和历史回放均不渲染到 UI
const SKILL_LOAD_TOOLS = new Set(['get_skill_instructions', 'get_skill_reference']);
export type LeftView = 'list' | 'chat';

interface WorkspaceState {
  // 视图
  leftView: LeftView;
  activeConversationId: string | null;

  // 消息（per conversation）
  messagesByConvId: Record<string, Message[]>;
  messagesLoadingConvIds: Set<string>;

  // 流式状态（per conversation）
  streamingConvIds: Set<string>;

  // 右侧渲染（per conversation 所有 render blocks）
  currentRenders: RenderBlock[];

  // 内部 abort controllers（per conversation）
  _abortCtrls: Record<string, AbortController>;

  // insight 流式 parser（per conversation）
  _insightParsers: Record<string, InsightEventParser>;

  // report 图表累积缓冲（per conversation，等 markdownReport 到达后一并存入 block）
  _reportChartsBuf: Record<string, ChartItem[]>;

  // Workspace 右侧报告视图（点击 ReportBubble 后设置）
  activeReport: { content: string; charts: ChartItem[] } | null;

  // actions
  setLeftView: (view: LeftView) => void;
  setActiveConversation: (id: string | null) => void;
  openConversation: (id: string) => void;
  startNewConversation: () => void;
  backToList: () => void;
  loadMessages: (id: string) => Promise<void>;
  sendMessage: (content: string, deepThinking: boolean) => Promise<void>;
  abortStream: (convId?: string) => void;
  setRenders: (blocks: RenderBlock[]) => void;
  setActiveReport: (report: { content: string; charts: ChartItem[] } | null) => void;
}

function newId(prefix: string) {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

/** 从历史 message 重建 blocks，包括从 renderBlocks 重建 report_ready */
function rebuildBlocks(m: Message): MessageBlock[] {
  const blocks: MessageBlock[] = [];
  if (m.thinkingContent?.trim()) {
    blocks.push({ type: 'thinking', content: m.thinkingContent, startedAt: 0, endedAt: 0 });
  }
  for (const step of m.steps ?? []) {
    step.completed = true;
    // 先过滤 subSteps（影响步骤计数）
    step.subSteps = step.subSteps.filter((sub) => !SKILL_LOAD_TOOLS.has(sub.name));
    if (!step.items?.length) {
      // 旧消息无 items，从 subSteps 重建（已过滤）
      step.items = step.subSteps.map((sub) => ({ type: 'sub_step' as const, data: sub }));
    } else {
      // 新消息 items 来自 API，直接过滤加载类条目
      step.items = step.items.filter(
        (item) => item.type !== 'sub_step' || !SKILL_LOAD_TOOLS.has(item.data.name),
      );
    }
    blocks.push({ type: 'step', stepId: step.stepId });
  }
  // experience_assurance 卡片在流式中于 steps 完成后、Orchestrator 总结文本之前到达，
  // 历史重建保持相同顺序：steps → experience_assurance → text
  for (const rb of m.renderBlocks ?? []) {
    if (rb.renderType === 'experience_assurance') {
      blocks.push({ type: 'experience_assurance', data: rb.renderData });
    }
  }

  if (m.content?.trim()) {
    blocks.push({ type: 'text', content: m.content });
  }
  // 从 renderBlocks 重建 report_ready block（insight 报告回放）
  // insight_query 每次查询产出单条 chart renderBlock（markdownReport=''），
  // insight_report 产出一条 markdownReport renderBlock（charts=[]）。
  // 历史回放需把所有图表合并，再配上 markdownReport，才能还原带插图的报告。
  const insightRBs = (m.renderBlocks ?? []).filter((rb) => rb.renderType === 'insight');
  const allCharts: ChartItem[] = insightRBs.flatMap((rb) => (rb.renderData as { charts?: ChartItem[] }).charts ?? []);
  const reportRB = insightRBs.find((rb) => (rb.renderData as { markdownReport?: string }).markdownReport?.trim());
  if (reportRB) {
    blocks.push({
      type: 'report_ready',
      content: (reportRB.renderData as { markdownReport: string }).markdownReport,
      charts: allCharts,
    });
  }

  return blocks;
}

/** 从历史 message 的 steps[].textContent 重解析 insightState */
function rebuildInsightState(m: Message): import('@/types/insight').InsightState | undefined {
  const parser = new InsightEventParser();
  let state: import('@/types/insight').InsightState | undefined;
  for (const step of m.steps ?? []) {
    const text = (step as Step & { textContent?: string }).textContent ?? '';
    if (!text) continue;
    const { events } = parser.feed(text);
    for (const evt of events) {
      state = applyInsightEvent(state, evt);
    }
  }
  return state;
}

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  leftView: 'list',
  activeConversationId: null,
  messagesByConvId: {},
  messagesLoadingConvIds: new Set(),
  streamingConvIds: new Set(),
  currentRenders: [],
  _abortCtrls: {},
  _insightParsers: {},
  _reportChartsBuf: {},
  activeReport: null,

  setLeftView: (view) => set({ leftView: view }),
  setActiveConversation: (id) => set({ activeConversationId: id }),

  openConversation: (id) => {
    set({ leftView: 'chat', activeConversationId: id, activeReport: null });
  },

  startNewConversation: () => {
    set({ leftView: 'chat', activeConversationId: null, activeReport: null, currentRenders: [] });
  },

  backToList: () => {
    set({ leftView: 'list', activeReport: null });
  },

  setActiveReport: (report) => set({ activeReport: report }),

  loadMessages: async (id) => {
    // 已有缓存则不重复请求，但仍需同步右侧渲染
    if (get().messagesByConvId[id]) {
      if (get().activeConversationId === id) {
        const cached = get().messagesByConvId[id];
        let lastRenders: RenderBlock[] = [];
        for (let i = cached.length - 1; i >= 0; i--) {
          const m = cached[i];
          if (m.role === 'assistant' && m.renderBlocks && m.renderBlocks.length > 0) {
            lastRenders = m.renderBlocks;
            break;
          }
        }
        set({ currentRenders: lastRenders });
      }
      return;
    }

    set((s) => ({ messagesLoadingConvIds: new Set([...s.messagesLoadingConvIds, id]) }));
    try {
      const resp = await getMessages(id);
      const list = (resp.list ?? []).map((m) => {
        if (m.role !== 'assistant') return m;
        return { ...m, blocks: rebuildBlocks(m), insightState: rebuildInsightState(m) };
      });
      let lastRenders: RenderBlock[] = [];
      for (let i = list.length - 1; i >= 0; i--) {
        const m = list[i];
        if (m.role === 'assistant' && m.renderBlocks && m.renderBlocks.length > 0) {
          lastRenders = m.renderBlocks;
          break;
        }
      }
      set((s) => ({
        messagesByConvId: { ...s.messagesByConvId, [id]: list },
        // 仅当切换到该会话时才更新右侧渲染
        currentRenders: s.activeConversationId === id ? lastRenders : s.currentRenders,
      }));
    } catch (e) {
      console.error('loadMessages failed', e);
      set((s) => ({ messagesByConvId: { ...s.messagesByConvId, [id]: [] } }));
    } finally {
      set((s) => {
        const next = new Set(s.messagesLoadingConvIds);
        next.delete(id);
        return { messagesLoadingConvIds: next };
      });
    }
  },

  sendMessage: async (content, deepThinking) => {
    const { activeConversationId, streamingConvIds } = get();
    if (!activeConversationId) return;
    const convId = activeConversationId;

    // 当前会话正在流式中则不重复发送
    if (streamingConvIds.has(convId)) return;

    // 首条消息时更新会话标题
    const existingMsgs = get().messagesByConvId[convId] ?? [];
    const isFirstMessage = existingMsgs.filter((m) => m.role === 'user').length === 0;
    if (isFirstMessage) {
      const title = content.trim().slice(0, 30);
      useConversationStore.getState().updateTitle(convId, title).catch(() => {});
    }

    // 追加用户消息
    const userMsg: Message = {
      id: newId('msg_user'),
      conversationId: convId,
      role: 'user',
      content,
      createdAt: new Date().toISOString(),
    };
    // 追加占位 assistant 消息
    const assistantId = newId('msg_asst');
    const assistantMsg: Message = {
      id: assistantId,
      conversationId: convId,
      role: 'assistant',
      content: '',
      thinkingContent: '',
      steps: [],
      renderBlocks: [],
      blocks: [],
      streaming: true,
      createdAt: new Date().toISOString(),
    };

    const appendMsgs = (prev: Message[]) => [...prev, userMsg, assistantMsg];
    set((s) => ({
      messagesByConvId: {
        ...s.messagesByConvId,
        [convId]: appendMsgs(s.messagesByConvId[convId] ?? []),
      },
      streamingConvIds: new Set([...s.streamingConvIds, convId]),
      // 切换到当前会话时清空右侧渲染
      currentRenders: s.activeConversationId === convId ? [] : s.currentRenders,
    }));

    const ctrl = new AbortController();
    set((s) => ({ _abortCtrls: { ...s._abortCtrls, [convId]: ctrl } }));

    // helper：immutable 更新指定会话的 assistant 消息
    const updateAssistant = (updater: (m: Message) => Message) => {
      set((s) => {
        const msgs = s.messagesByConvId[convId] ?? [];
        return {
          messagesByConvId: {
            ...s.messagesByConvId,
            [convId]: msgs.map((m) => (m.id === assistantId ? updater(m) : m)),
          },
        };
      });
    };

    try {
      const resp = await sendMessageStream(convId, { content, deepThinking }, ctrl.signal);
      const sseLog: { event: string; data: unknown }[] = [];
      await parseSseStream(
        resp,
        (e) => {
          sseLog.push({ event: e.event, data: e.data });
          switch (e.event) {
            case 'thinking': {
              const d = e.data as ThinkingEvent;
              if (d.stepId) {
                updateAssistant((m) => ({
                  ...m,
                  steps: (m.steps ?? []).map((s) => {
                    if (s.stepId !== d.stepId) return s;
                    const items = s.items ?? [];
                    const last = items[items.length - 1];
                    if (last?.type === 'thinking' && !last.endedAt) {
                      return {
                        ...s,
                        items: [
                          ...items.slice(0, -1),
                          { ...last, content: last.content + d.delta },
                        ],
                      };
                    }
                    return {
                      ...s,
                      items: [
                        ...items,
                        { type: 'thinking' as const, content: d.delta, startedAt: Date.now() },
                      ],
                    };
                  }),
                }));
              } else {
                updateAssistant((m) => {
                  const blocks = m.blocks ?? [];
                  const last = blocks[blocks.length - 1];
                  const newBlocks: MessageBlock[] =
                    last?.type === 'thinking' && !last.endedAt
                      ? [...blocks.slice(0, -1), { ...last, content: last.content + d.delta }]
                      : [...blocks, { type: 'thinking', content: d.delta, startedAt: Date.now() }];
                  return { ...m, blocks: newBlocks, thinkingContent: (m.thinkingContent ?? '') + d.delta };
                });
              }
              break;
            }
            case 'text': {
              const d = e.data as TextEvent;
              // 确保该会话有 parser 实例
              if (!get()._insightParsers[convId]) {
                set((s) => ({
                  _insightParsers: { ...s._insightParsers, [convId]: new InsightEventParser() },
                }));
              }
              const parser = get()._insightParsers[convId];
              const { cleanText, events } = parser.feed(d.delta);

              updateAssistant((m) => {
                let next = m;

                // 应用 insight 事件到 insightState
                if (events.length > 0) {
                  let insightState = m.insightState;
                  for (const evt of events) {
                    insightState = applyInsightEvent(insightState, evt);
                  }
                  next = { ...next, insightState };
                }

                // cleanText 写入 blocks / step.items（原逻辑，用 cleanText 替代 delta）
                if (cleanText) {
                  const steps = next.steps ?? [];
                  const lastStep = steps[steps.length - 1];
                  if (lastStep && !lastStep.completed) {
                    const newSteps = steps.map((s) => {
                      if (s.stepId !== lastStep.stepId) return s;
                      const items = s.items ?? [];
                      const lastItem = items[items.length - 1];
                      const newItems =
                        lastItem?.type === 'text'
                          ? [...items.slice(0, -1), { type: 'text' as const, content: lastItem.content + cleanText }]
                          : [...items, { type: 'text' as const, content: cleanText }];
                      return { ...s, items: newItems };
                    });
                    next = { ...next, steps: newSteps, content: next.content + cleanText };
                  } else {
                    const blocks = next.blocks ?? [];
                    const last = blocks[blocks.length - 1];
                    const closedBlocks = last?.type === 'thinking' && !last.endedAt
                      ? [...blocks.slice(0, -1), { ...last, endedAt: Date.now() }]
                      : blocks;
                    const prevLast = closedBlocks[closedBlocks.length - 1];
                    const newBlocks: MessageBlock[] =
                      prevLast?.type === 'text'
                        ? [...closedBlocks.slice(0, -1), { type: 'text', content: prevLast.content + cleanText }]
                        : [...closedBlocks, { type: 'text', content: cleanText }];
                    next = { ...next, blocks: newBlocks, content: next.content + cleanText };
                  }
                }

                return next;
              });
              break;
            }
            case 'step_start': {
              const d = e.data as StepStartEvent;
              const newStep: Step = { stepId: d.stepId, title: d.title, subSteps: [], items: [] };
              updateAssistant((m) => {
                const blocks = m.blocks ?? [];
                const last = blocks[blocks.length - 1];
                const closedBlocks = last?.type === 'thinking' && !last.endedAt
                  ? [...blocks.slice(0, -1), { ...last, endedAt: Date.now() }]
                  : blocks;
                return {
                  ...m,
                  blocks: [...closedBlocks, { type: 'step', stepId: d.stepId }],
                  steps: [...(m.steps ?? []), newStep],
                };
              });
              break;
            }
            case 'sub_step': {
              const d = e.data as SubStepEvent;
              if (SKILL_LOAD_TOOLS.has(d.name)) break;   // 过滤掉某些子步骤

              const sub: SubStep = {
                subStepId: d.subStepId,
                name: d.name,
                scriptPath: d.scriptPath,
                callArgs: d.callArgs,
                stdout: d.stdout,
                stderr: d.stderr,
                completedAt: d.completedAt,
                durationMs: d.durationMs,
              };
              updateAssistant((m) => ({
                ...m,
                steps: (m.steps ?? []).map((s) => {
                  if (s.stepId !== d.stepId) return s;
                  const closedItems = (s.items ?? []).map((item, idx) =>
                    idx === s.items.length - 1 && item.type === 'thinking' && !item.endedAt
                      ? { ...item, endedAt: Date.now() }
                      : item,
                  );
                  return {
                    ...s,
                    subSteps: [...s.subSteps, sub],
                    items: [...closedItems, { type: 'sub_step' as const, data: sub }],
                  };
                }),
              }));
              break;
            }
            case 'step_end': {
              const d = e.data as StepEndEvent;
              updateAssistant((m) => ({
                ...m,
                steps: (m.steps ?? []).map((s) => {
                  if (s.stepId !== d.stepId) return s;
                  const closedItems = (s.items ?? []).map((item, idx) =>
                    idx === s.items.length - 1 && item.type === 'thinking' && !item.endedAt
                      ? { ...item, endedAt: Date.now() }
                      : item,
                  );
                  return { ...s, completed: true, items: closedItems };
                }),
              }));
              break;
            }
            case 'render': {
              const block = e.data as RenderBlock;
              // image 类型改由 wifi_result 事件处理，此处跳过
              if (block.renderType === 'image') break;
              updateAssistant((m) => ({
                ...m,
                renderBlocks: [...(m.renderBlocks ?? []), block],
              }));
              if (get().activeConversationId === convId) {
                set((s) => ({ currentRenders: [...s.currentRenders, block] }));
              }
              break;
            }
            case 'wifi_result': {
              const d = e.data as WifiResultEvent;
              const imageBlocks: RenderBlock[] = d.renderData.images.map((img) => ({
                renderType: 'image' as const,
                renderData: {
                  imageId: img.imageId,
                  imageUrl: img.imageUrl,
                  title: img.title,
                  kind: img.kind,
                },
              }));
              updateAssistant((m) => ({
                ...m,
                renderBlocks: [...(m.renderBlocks ?? []), ...imageBlocks],
              }));
              if (get().activeConversationId === convId) {
                set((s) => ({ currentRenders: [...s.currentRenders, ...imageBlocks] }));
              }
              break;
            }
            case 'experience_assurance_result': {
              const d = e.data as ExperienceAssuranceResultEvent;
              const rb: RenderBlock = {
                renderType: 'experience_assurance',
                renderData: d.renderData,
              };
              updateAssistant((m) => ({
                ...m,
                blocks: [...(m.blocks ?? []), { type: 'experience_assurance', data: d.renderData }],
                renderBlocks: [...(m.renderBlocks ?? []), rb],
              }));
              break;
            }
            case 'report': {
              const d = e.data as ReportEvent;
              const { charts, markdownReport } = d.renderData;
              // 有图表数据：累积到缓冲区
              if (charts.length > 0) {
                set((s) => ({
                  _reportChartsBuf: {
                    ...s._reportChartsBuf,
                    [convId]: [...(s._reportChartsBuf[convId] ?? []), ...charts],
                  },
                }));
              }
              // markdownReport 非空：报告完整，写入 report_ready block 并清空缓冲
              if (markdownReport.trim()) {
                const accumulated = get()._reportChartsBuf[convId] ?? [];
                updateAssistant((m) => ({
                  ...m,
                  blocks: [
                    ...(m.blocks ?? []),
                    { type: 'report_ready', content: markdownReport, charts: accumulated },
                  ],
                }));
                set((s) => {
                  const buf = { ...s._reportChartsBuf };
                  delete buf[convId];
                  return { _reportChartsBuf: buf };
                });
              }
              break;
            }
            case 'done': {
              const d = e.data as DoneEvent;
              updateAssistant((m) => {
                const blocks = m.blocks ?? [];
                const last = blocks[blocks.length - 1];
                const closedBlocks = last?.type === 'thinking' && !last.endedAt
                  ? [...blocks.slice(0, -1), { ...last, endedAt: Date.now() }]
                  : blocks;
                return {
                  ...m,
                  blocks: closedBlocks,
                  streaming: false,
                  thinkingDurationSec: d.thinkingDurationSec,
                };
              });
              break;
            }
            case 'error': {
              const d = e.data as SseErrorEvent;
              updateAssistant((m) => ({ ...m, streaming: false, error: d.message }));
              break;
            }
            default:
              break;
          }
        },
        ctrl.signal,
      );

      // 开发模式写 SSE 日志
      if (import.meta.env.DEV && sseLog.length > 0) {
        fetch('/dev/sse-log', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ convId, events: sseLog }),
        }).catch(() => {});
      }
    } catch (err) {
      if ((err as Error)?.name === 'AbortError') {
        // 主动中止，不视为错误
      } else {
        const msg = (err as Error)?.message || '网络错误';
        updateAssistant((m) => ({ ...m, streaming: false, error: msg }));
      }
    } finally {
      set((s) => {
        const nextStreaming = new Set(s.streamingConvIds);
        nextStreaming.delete(convId);
        const nextCtrls = { ...s._abortCtrls };
        delete nextCtrls[convId];
        const nextParsers = { ...s._insightParsers };
        delete nextParsers[convId];
        return { streamingConvIds: nextStreaming, _abortCtrls: nextCtrls, _insightParsers: nextParsers };
      });
    }
  },

  abortStream: (convId?: string) => {
    const id = convId ?? get().activeConversationId;
    if (!id) return;
    const ctrl = get()._abortCtrls[id];
    if (ctrl) {
      ctrl.abort();
      set((s) => {
        const nextStreaming = new Set(s.streamingConvIds);
        nextStreaming.delete(id);
        const nextCtrls = { ...s._abortCtrls };
        delete nextCtrls[id];
        return { streamingConvIds: nextStreaming, _abortCtrls: nextCtrls };
      });
    }
  },

  setRenders: (blocks) => set({ currentRenders: blocks }),
}));
