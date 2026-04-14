import { useEffect, useMemo, useState } from 'react';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useWorkspaceStore } from '@/store/workspaceStore';
import { useConversationStore } from '@/store/conversationStore';
import MessageList from './MessageList';
import InputBubble from './InputBubble';
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
  const [editDraft, setEditDraft] = useState(prefillMessage ?? '');

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

      <div className={styles.body}>
        <MessageList
          messages={messages}
          loading={messagesLoading}
          isStreaming={isStreaming}
          onViewReport={(content, charts) => setActiveReport({ content, charts })}
          onEditMessage={(content) => {
            if (isStreaming && activeId) {
              // 中止当前会话的流，移除未完成的 assistant 消息
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
        />
      </div>

      <InputBubble
        disabled={!activeId}
        onSend={(content, deepThinking) => {
          if (isStreaming) return;
          setEditDraft('');
          if (messages.length === 0 && activeId) {
            updateTitle(activeId, `用户级入口-${content.slice(0, 20)}`);
          }
          sendMessage(content, deepThinking);
        }}
        fillValue={editDraft}
      />
    </div>
  );
}

export default ChatView;
