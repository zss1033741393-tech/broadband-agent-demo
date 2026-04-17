import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useWorkspaceStore } from '@/store/workspaceStore';
import { useConversationStore } from '@/store/conversationStore';
import { useSimulationStore } from '@/store/simulationStore';
import { matchSimCommand, FAULT_NAMES } from '@/utils/simulationMatcher';
import { getProtectionPlan, type PlanGroup } from '@/api/protectionPlan';
import MessageList from './MessageList';
import ProtectionPlanCard from './ProtectionPlanCard';
import InputBubble from './InputBubble';
import InsightPhasePanel from './InsightPhasePanel';
import SimBubble from './SimBubble';
import styles from './ChatView.module.css';
import simListStyles from './SimList.module.css';
import type { ConversationSource } from '@/types/conversation';
import type { Message } from '@/types/message';

interface Props {
  prefillMessage?: string;
  /** 无 activeId 时首次发消息才创建会话，并标记该来源 */
  lazySource?: ConversationSource;
}

function ChatView({ prefillMessage, lazySource }: Props) {
  const [planGroups, setPlanGroups] = useState<PlanGroup[]>([]);

  const fetchPlan = useCallback(async () => {
    if (!prefillMessage) return;
    try {
      const data = await getProtectionPlan();
      setPlanGroups(data.groups);
    } catch {
      setPlanGroups([]);
    }
  }, [prefillMessage]);

  useEffect(() => { fetchPlan(); }, [fetchPlan]);

  const fixedPrefillReply = useMemo<Message[]>(
    () =>
      prefillMessage
        ? [
            {
              id: 'prefill_plan_card',
              conversationId: '',
              role: 'assistant',
              content: '',
              blocks: [{ type: 'protection_plan' as const }],
              createdAt: new Date(0).toISOString(),
            },
          ]
        : [],
    [prefillMessage],
  );

  const backToList = useWorkspaceStore((s) => s.backToList);
  const setActiveReport = useWorkspaceStore((s) => s.setActiveReport);
  const activeId = useWorkspaceStore((s) => s.activeConversationId);
  const setActiveConversation = useWorkspaceStore((s) => s.setActiveConversation);
  const messagesByConvId = useWorkspaceStore((s) => s.messagesByConvId);
  const messagesLoadingConvIds = useWorkspaceStore((s) => s.messagesLoadingConvIds);
  const streamingConvIds = useWorkspaceStore((s) => s.streamingConvIds);
  const loadMessages = useWorkspaceStore((s) => s.loadMessages);
  const sendMessage = useWorkspaceStore((s) => s.sendMessage);
  const abortStream = useWorkspaceStore((s) => s.abortStream);

  const conversations = useConversationStore((s) => s.list);
  const createConversation = useConversationStore((s) => s.create);
  const updateTitle = useConversationStore((s) => s.updateTitle);
  const setSource = useConversationStore((s) => s.setSource);
  const [editDraft, setEditDraft] = useState(prefillMessage ?? '');
  const [progressCollapsed, setProgressCollapsed] = useState(false);
  const creating = useRef(false);

  // ── Simulation store ───────────────────────────────────────────────────────
  const simActive = useSimulationStore((s) => s.active);
  const simStreaming = useSimulationStore((s) => s.streaming);
  const simEvents = useSimulationStore((s) => s.simEvents);
  const simConvIdRef = useRef<string | null>(null);
  const simListRef = useRef<HTMLDivElement>(null);

  const messages = activeId ? (messagesByConvId[activeId] ?? []) : [];
  const visibleMessages = messages.length === 0 ? fixedPrefillReply : messages;
  const messagesLoading = activeId ? messagesLoadingConvIds.has(activeId) : false;
  const isStreaming = activeId ? streamingConvIds.has(activeId) : false;

  const title = useMemo(() => {
    if (!activeId) return '对话';
    return conversations.find((c) => c.id === activeId)?.title ?? '新对话';
  }, [activeId, conversations]);

  useEffect(() => {
    if (activeId) {
      loadMessages(activeId);
    }
  }, [activeId, loadMessages]);

  // Auto-scroll sim events list on new events
  useEffect(() => {
    if (simListRef.current) {
      simListRef.current.scrollTop = simListRef.current.scrollHeight;
    }
  }, [simEvents.length]);

  // 从最后一条 assistant 消息中提取进度数据
  const lastAssistant = [...visibleMessages].reverse().find((m) => m.role === 'assistant');
  const insightState = lastAssistant?.insightState ?? null;
  const steps = lastAssistant?.steps ?? [];
  const allBlocks = visibleMessages.flatMap((m) => m.blocks ?? []);
  const reportBlock = [...allBlocks].reverse().find((b) => b.type === 'report_ready');

  // 有任意 step 或 insightState → 显示进度跟踪面板
  const hasProgress = steps.length > 0 || insightState !== null;

  const handleSend = async (content: string, deepThinking: boolean) => {
    // ── Simulation command intercept ──────────────────────────────────────────
    const simAction = matchSimCommand(content);

    if (simAction !== null) {
      const store = useSimulationStore.getState();

      if (simAction.type === 'unknown_sim_cmd') {
        store.addUserEvent(content);
        const isUnknownFault = /^仿真故障/.test(content);
        store.addSystemEvent(
          isUnknownFault
            ? `未识别的故障名称。支持的故障：${FAULT_NAMES.join(' / ')}`
            : `支持的仿真指令：仿真：启动 / 仿真故障：<故障名>`,
        );
        return;
      }

      if (simAction.type === 'start') {
        const convId = activeId ?? `sim-${Date.now()}`;
        simConvIdRef.current = convId;
        store.addUserEvent('仿真：启动');
        void store.startSimulation(convId);
        return;
      }

      if (simAction.type === 'inject_fault') {
        if (!store.active) {
          store.addUserEvent(content);
          store.addSystemEvent('请先输入"仿真：启动"运行基线仿真，再注入故障。');
          return;
        }
        if (store.streaming) {
          store.addUserEvent(content);
          store.addSystemEvent('仿真进行中，请等待当前段完成后再注入故障。');
          return;
        }
        const convId = simConvIdRef.current ?? store.convId ?? `sim-${Date.now()}`;
        simConvIdRef.current = convId;
        store.addUserEvent(content);
        void store.injectFault(convId, simAction.faultName);
        return;
      }

      return;
    }

    // ── Regular Agent flow ────────────────────────────────────────────────────
    if (isStreaming || creating.current) return;
    setEditDraft('');

    let convId = activeId;

    // lazySource 模式：无 activeId 时首次发消息才创建会话
    if (!convId && lazySource) {
      creating.current = true;
      try {
        const conv = await createConversation();
        setSource(conv.id, lazySource);
        setActiveConversation(conv.id);
        convId = conv.id;
      } catch {
        creating.current = false;
        return;
      }
      creating.current = false;
    }

    if (!convId) return;

    if (messages.length === 0) {
      updateTitle(convId, content.slice(0, 30));
      if (!lazySource) setSource(convId, 'workspace');
    }
    sendMessage(content, deepThinking);
  };

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <button
          type="button"
          className={styles.backBtn}
          onClick={backToList}
          aria-label="返回会话列表"
        >
          <ArrowLeftOutlined />
        </button>
        <h2 className={styles.title} title={simActive ? 'RTMP 推流仿真' : title}>
          {simActive ? 'RTMP 推流仿真' : title}
        </h2>
      </header>

      {/* 进度跟踪面板：仅非仿真模式下显示 */}
      {!simActive && hasProgress && (
        <InsightPhasePanel
          state={insightState ?? undefined}
          steps={steps.length > 0 ? steps : undefined}
          isStreaming={isStreaming}
          collapsed={progressCollapsed}
          onToggle={() => setProgressCollapsed((v) => !v)}
          reportContent={reportBlock?.type === 'report_ready' ? reportBlock.content : undefined}
          reportCharts={reportBlock?.type === 'report_ready' ? reportBlock.charts : undefined}
          onViewReport={(content, charts) => setActiveReport({ content, charts })}
        />
      )}

      <div className={styles.body}>
        {simActive ? (
          /* ── 仿真模式：显示 SimBubble 事件流 ── */
          <div className={simListStyles.scroll} ref={simListRef}>
            <div className={simListStyles.list}>
              {simEvents.map((evt) => (
                <SimBubble key={evt.id} event={evt} />
              ))}
              {simStreaming && (
                <div className={simListStyles.streamingHint}>仿真数据推送中...</div>
              )}
            </div>
          </div>
        ) : (
          /* ── 普通模式：Agent 消息列表 ── */
          <MessageList
            messages={visibleMessages}
            loading={messagesLoading}
            isStreaming={isStreaming}
            planGroups={planGroups}
            onEditMessage={(content) => {
              if (isStreaming && activeId) {
                abortStream(activeId);
                const msgs = useWorkspaceStore.getState().messagesByConvId[activeId] ?? [];
                const last = msgs[msgs.length - 1];
                if (last?.role === 'assistant' && last.streaming) {
                  useWorkspaceStore.setState((s) => ({
                    messagesByConvId: {
                      ...s.messagesByConvId,
                      [activeId]: msgs.slice(0, -1),
                    },
                  }));
                }
              }
              setEditDraft(content);
            }}
            hideInsightPanel={hasProgress}
            onViewReport={hasProgress ? undefined : (content, charts) => setActiveReport({ content, charts })}
          />
        )}
      </div>

      <InputBubble
        disabled={isStreaming || simStreaming}
        onSend={handleSend}
        fillValue={editDraft}
        disabledPlaceholder={simStreaming ? '仿真进行中...' : 'Agent 处理中...'}
      />
    </div>
  );
}

export default ChatView;
