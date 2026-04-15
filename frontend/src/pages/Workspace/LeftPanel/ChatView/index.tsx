import { useEffect, useMemo, useState } from 'react';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useWorkspaceStore } from '@/store/workspaceStore';
import { useConversationStore } from '@/store/conversationStore';
import MessageList from './MessageList';
import InputBubble from './InputBubble';
import InsightPhasePanel from './InsightPhasePanel';
import styles from './ChatView.module.css';

interface Props {
  prefillMessage?: string;
}

function ChatView({ prefillMessage }: Props) {
  const backToList = useWorkspaceStore((s) => s.backToList);
  const setActiveReport = useWorkspaceStore((s) => s.setActiveReport);
  const activeId = useWorkspaceStore((s) => s.activeConversationId);
  const messagesByConvId = useWorkspaceStore((s) => s.messagesByConvId);
  const messagesLoadingConvIds = useWorkspaceStore((s) => s.messagesLoadingConvIds);
  const streamingConvIds = useWorkspaceStore((s) => s.streamingConvIds);
  const loadMessages = useWorkspaceStore((s) => s.loadMessages);
  const sendMessage = useWorkspaceStore((s) => s.sendMessage);
  const abortStream = useWorkspaceStore((s) => s.abortStream);

  const conversations = useConversationStore((s) => s.list);
  const updateTitle = useConversationStore((s) => s.updateTitle);
  const setSource = useConversationStore((s) => s.setSource);
  const [editDraft, setEditDraft] = useState(prefillMessage ?? '');
  const [progressCollapsed, setProgressCollapsed] = useState(false);

  const messages = activeId ? (messagesByConvId[activeId] ?? []) : [];
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

  // 从最后一条 assistant 消息中提取进度数据
  const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant');
  const insightState = lastAssistant?.insightState ?? null;
  const steps = lastAssistant?.steps ?? [];
  const allBlocks = messages.flatMap((m) => m.blocks ?? []);
  const reportBlock = [...allBlocks].reverse().find((b) => b.type === 'report_ready');

  // 有任意 step 或 insightState → 显示进度跟踪面板
  const hasProgress = steps.length > 0 || insightState !== null;

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
        <h2 className={styles.title} title={title}>
          {title}
        </h2>
      </header>

      {/* 进度跟踪面板：有 step 或 insightState 时悬浮在顶部 */}
      {hasProgress && (
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
        <MessageList
          messages={messages}
          loading={messagesLoading}
          isStreaming={isStreaming}
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
      </div>

      <InputBubble
        disabled={!activeId}
        onSend={(content, deepThinking) => {
          if (isStreaming) return;
          setEditDraft('');
          if (messages.length === 0 && activeId) {
            setSource(activeId, 'workspace');
            updateTitle(activeId, content.slice(0, 30));
          }
          sendMessage(content, deepThinking);
        }}
        fillValue={editDraft}
      />
    </div>
  );
}

export default ChatView;
