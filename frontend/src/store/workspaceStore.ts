import { create } from 'zustand';
import { getMessages, sendMessageStream } from '@/api/messages';

import { useConversationStore } from '@/store/conversationStore';
import { parseSseStream } from '@/utils/sseParser';
import type { Message, Step, SubStep, MessageBlock } from '@/types/message';
import type { RenderBlock } from '@/types/render';
import type {
  DoneEvent,
  ErrorEvent as SseErrorEvent,
  StepStartEvent,
  StepEndEvent,
  SubStepEvent,
  TextEvent,
  ThinkingEvent,
} from '@/types/sse';

export type LeftView = 'list' | 'chat';

interface WorkspaceState {
  // 视图
  leftView: LeftView;
  activeConversationId: string | null;

  // 消息流
  messages: Message[];
  messagesLoading: boolean;
  isStreaming: boolean;

  // 右侧渲染
  currentRender: RenderBlock | null;

  // 内部 abort controller
  _abortCtrl: AbortController | null;

  // actions
  setLeftView: (view: LeftView) => void;
  setActiveConversation: (id: string | null) => void;
  openConversation: (id: string) => void;
  backToList: () => void;
  loadMessages: (id: string) => Promise<void>;
  sendMessage: (content: string, deepThinking: boolean) => Promise<void>;
  abortStream: () => void;
  setRender: (block: RenderBlock | null) => void;
}

function newId(prefix: string) {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

/** 从历史 message 重建 blocks（历史无顺序信息，按 thinking→steps→text 重建） */
function rebuildBlocks(m: Message): MessageBlock[] {
  const blocks: MessageBlock[] = [];
  if (m.thinkingContent?.trim()) {
    // 历史消息无时间戳，startedAt/endedAt 用 0 占位，durationSec 显示为 thinkingDurationSec
    blocks.push({ type: 'thinking', content: m.thinkingContent, startedAt: 0, endedAt: 0 });
  }
  for (const step of m.steps ?? []) {
    // 历史消息的 step：items 从 subSteps 重建，无 thinking 信息
    step.completed = true;
    step.items = step.subSteps.map((sub) => ({ type: 'sub_step' as const, data: sub }));
    blocks.push({ type: 'step', stepId: step.stepId });
  }
  if (m.content?.trim()) {
    blocks.push({ type: 'text', content: m.content });
  }
  return blocks;
}

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  leftView: 'list',
  activeConversationId: null,
  messages: [],
  messagesLoading: false,
  isStreaming: false,
  currentRender: null,
  _abortCtrl: null,

  setLeftView: (view) => set({ leftView: view }),
  setActiveConversation: (id) => set({ activeConversationId: id }),

  openConversation: (id) => {
    get().abortStream();
    set({
      leftView: 'chat',
      activeConversationId: id,
      messages: [],
      currentRender: null,
    });
  },

  backToList: () => {
    get().abortStream();
    set({ leftView: 'list' });
  },

  loadMessages: async (id) => {
    set({ messagesLoading: true });
    try {
      const resp = await getMessages(id);
      const list = (resp.list ?? []).map((m) => {
        if (m.role !== 'assistant') return m;
        return { ...m, blocks: rebuildBlocks(m) };
      });
      // 恢复右侧最后一条 renderBlock
      let lastRender: RenderBlock | null = null;
      for (let i = list.length - 1; i >= 0; i--) {
        const m = list[i];
        if (m.role === 'assistant' && m.renderBlocks && m.renderBlocks.length > 0) {
          lastRender = m.renderBlocks[m.renderBlocks.length - 1];
          break;
        }
      }
      set({ messages: list, currentRender: lastRender });
    } catch (e) {
      console.error('loadMessages failed', e);
      set({ messages: [] });
    } finally {
      set({ messagesLoading: false });
    }
  },

  sendMessage: async (content, deepThinking) => {
    const { activeConversationId, isStreaming, messages } = get();
    if (!activeConversationId || isStreaming) return;

    // 首条消息时用 query 作为会话标题
    const isFirstMessage = messages.filter((m) => m.role === 'user').length === 0;
    if (isFirstMessage) {
      const title = content.trim().slice(0, 30);
      useConversationStore.getState().updateTitle(activeConversationId, title).catch(() => {});
    }

    // 1) 立即追加用户消息
    const userMsg: Message = {
      id: newId('msg_user'),
      conversationId: activeConversationId,
      role: 'user',
      content,
      createdAt: new Date().toISOString(),
    };
    // 2) 追加占位 assistant 消息（流式中）
    const assistantId = newId('msg_asst');
    const assistantMsg: Message = {
      id: assistantId,
      conversationId: activeConversationId,
      role: 'assistant',
      content: '',
      thinkingContent: '',
      steps: [],
      renderBlocks: [],
      blocks: [],
      streaming: true,
      createdAt: new Date().toISOString(),
    };
    set({
      messages: [...get().messages, userMsg, assistantMsg],
      isStreaming: true,
      currentRender: null,
    });

    const ctrl = new AbortController();
    set({ _abortCtrl: ctrl });

    // helper：immutable 更新最后一条 assistant
    const updateAssistant = (updater: (m: Message) => Message) => {
      set({
        messages: get().messages.map((m) => (m.id === assistantId ? updater(m) : m)),
      });
    };

    try {
      const resp = await sendMessageStream(
        activeConversationId,
        { content, deepThinking },
        ctrl.signal,
      );
      const sseLog: { event: string; data: unknown }[] = [];
      await parseSseStream(
        resp,
        (e) => {
          sseLog.push({ event: e.event, data: e.data });
          switch (e.event) {
            case 'thinking': {
              const d = e.data as ThinkingEvent;
              if (d.stepId) {
                // SubAgent 思考：追加到 step 的 items[]
                updateAssistant((m) => ({
                  ...m,
                  steps: (m.steps ?? []).map((s) => {
                    if (s.stepId !== d.stepId) return s;
                    const items = s.items ?? [];
                    const last = items[items.length - 1];
                    if (last?.type === 'thinking' && !last.endedAt) {
                      // 追加到当前 thinking block
                      return {
                        ...s,
                        items: [
                          ...items.slice(0, -1),
                          { ...last, content: last.content + d.delta },
                        ],
                      };
                    }
                    // 新建 thinking block，前端打开始时间戳
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
                // Orchestrator 思考：追加到 blocks[] 的 thinking block
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
              updateAssistant((m) => {
                const blocks = m.blocks ?? [];
                const last = blocks[blocks.length - 1];
                // 关闭前一个 thinking block（如果有）
                const closedBlocks = last?.type === 'thinking' && !last.endedAt
                  ? [...blocks.slice(0, -1), { ...last, endedAt: Date.now() }]
                  : blocks;
                const prevLast = closedBlocks[closedBlocks.length - 1];
                const newBlocks: MessageBlock[] =
                  prevLast?.type === 'text'
                    ? [...closedBlocks.slice(0, -1), { type: 'text', content: prevLast.content + d.delta }]
                    : [...closedBlocks, { type: 'text', content: d.delta }];
                return { ...m, blocks: newBlocks, content: m.content + d.delta };
              });
              break;
            }
            case 'step_start': {
              const d = e.data as StepStartEvent;
              const newStep: Step = { stepId: d.stepId, title: d.title, subSteps: [], items: [] };
              updateAssistant((m) => {
                const blocks = m.blocks ?? [];
                const last = blocks[blocks.length - 1];
                // 关闭前一个 thinking block（如果有）
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
                  // 关闭当前正在流式的 thinking block（打 endedAt 时间戳）
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
                  // 关闭最后一个 thinking block（如果有）
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
              updateAssistant((m) => ({
                ...m,
                renderBlocks: [...(m.renderBlocks ?? []), block],
              }));
              set({ currentRender: block });
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
              updateAssistant((m) => ({
                ...m,
                streaming: false,
                error: d.message,
              }));
              break;
            }
            default:
              break;
          }
        },
        ctrl.signal,
      );
    } catch (err) {
      if ((err as Error)?.name === 'AbortError') {
        // 主动中止，不视为错误
      } else {
        const msg = (err as Error)?.message || '网络错误';
        updateAssistant((m) => ({ ...m, streaming: false, error: msg }));
      }
    } finally {
      set({ isStreaming: false, _abortCtrl: null });
      // 开发模式下将 SSE 日志写入本地文件
      if (import.meta.env.DEV && sseLog.length > 0) {
        fetch('/dev/sse-log', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ convId: activeConversationId, events: sseLog }),
        }).catch(() => {});
      }
    }
  },

  abortStream: () => {
    const ctrl = get()._abortCtrl;
    if (ctrl) {
      ctrl.abort();
      set({ _abortCtrl: null, isStreaming: false });
    }
  },

  setRender: (block) => set({ currentRender: block }),
}));
