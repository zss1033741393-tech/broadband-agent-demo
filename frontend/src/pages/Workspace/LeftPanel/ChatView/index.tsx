import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useWorkspaceStore } from '@/store/workspaceStore';
import { useConversationStore } from '@/store/conversationStore';
import MessageList from './MessageList';
import InputBubble from './InputBubble';
import InsightPhasePanel from './InsightPhasePanel';
import styles from './ChatView.module.css';
import type { ConversationSource } from '@/types/conversation';
import type { Message } from '@/types/message';

interface Props {
  prefillMessage?: string;
  /** 无 activeId 时首次发消息才创建会话，并标记该来源 */
  lazySource?: ConversationSource;
}

function ChatView({ prefillMessage, lazySource }: Props) {
  const fixedPrefillReply = useMemo<Message[]>(
    () =>
      prefillMessage
        ? [
            {
              id: 'prefill_fixed_reply',
              conversationId: '',
              role: 'assistant',
              content: '这是一条固定信息返回\n\n这是一条固定信息返回\n\n这是一条固定信息返回\n\n这是一条固定信息返回\n\n这是一条固定信息返回',
              blocks: [{ type: 'text', content: '这是一条固定信息返回\n\n这是一条固定信息返回\n\n这是一条固定信息返回\n\n这是一条固定信息返回\n\n这是一条固定信息返回' }],
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

  // 从最后一条 assistant 消息中提取进度数据
  const lastAssistant = [...visibleMessages].reverse().find((m) => m.role === 'assistant');
  const insightState = lastAssistant?.insightState ?? null;
  const steps = lastAssistant?.steps ?? [];
  const allBlocks = visibleMessages.flatMap((m) => m.blocks ?? []);
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
          messages={visibleMessages}
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
        disabled={isStreaming}
        onSend={async (content, deepThinking) => {
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
        }}
        fillValue={editDraft}
      />
    </div>
  );
}

export default ChatView;
