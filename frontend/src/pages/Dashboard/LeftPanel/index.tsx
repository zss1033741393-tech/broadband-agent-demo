import { useEffect, useRef, useState } from 'react';
import { useWorkspaceStore } from '@/store/workspaceStore';
import { useConversationStore } from '@/store/conversationStore';
import StatBar from './StatBar';
import EventCards from './EventCards';
import ChatSection from './ChatSection';
import MessageList from '@/pages/Workspace/LeftPanel/ChatView/MessageList';
import InputBubble from '@/pages/Workspace/LeftPanel/ChatView/InputBubble';
import styles from './LeftPanel.module.css';

/**
 * Dashboard 左侧面板：
 * - 默认模式：StatBar + Banner + EventCards + ChatSection（固定结论 + 输入框）
 * - 对话模式：用户首次发问后，整个左侧切换为纯 QA 对话视图
 */
function DashboardLeftPanel() {
  const [convId, setConvId] = useState<string | null>(null);
  const [chatMode, setChatMode] = useState(false);

  const messagesByConvId = useWorkspaceStore((s) => s.messagesByConvId);
  const streamingConvIds = useWorkspaceStore((s) => s.streamingConvIds);
  const messagesLoadingConvIds = useWorkspaceStore((s) => s.messagesLoadingConvIds);
  const sendMessage = useWorkspaceStore((s) => s.sendMessage);
  const setActiveConversation = useWorkspaceStore((s) => s.setActiveConversation);
  const createConversation = useConversationStore((s) => s.create);

  const initiated = useRef(false);

  useEffect(() => {
    if (initiated.current) return;
    initiated.current = true;
    (async () => {
      try {
        const conv = await createConversation('Dashboard 对话');
        setConvId(conv.id);
        setActiveConversation(conv.id);
      } catch {
        initiated.current = false;
      }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [convId]);

  const messages = convId ? (messagesByConvId[convId] ?? []) : [];
  const isStreaming = convId ? streamingConvIds.has(convId) : false;
  const isLoading = convId ? messagesLoadingConvIds.has(convId) : false;

  const handleSend = (content: string, deepThinking: boolean) => {
    if (!convId || isStreaming) return;
    setActiveConversation(convId);
    setChatMode(true);
    sendMessage(content, deepThinking);
  };

  const inputBubble = (
    <div className={styles.inputArea}>
      <InputBubble
        inline
        disabled={!convId || isStreaming}
        disabledPlaceholder={!convId ? '初始化中...' : 'Agent 处理中...'}
        onSend={handleSend}
      />
    </div>
  );

  if (chatMode) {
    return (
      <aside className={styles.leftPanel}>
        <div className={styles.chatFullArea}>
          <MessageList
            messages={messages}
            loading={isLoading}
            isStreaming={isStreaming}
            onEditMessage={() => {}}
          />
        </div>
        {inputBubble}
      </aside>
    );
  }

  return (
    <aside className={styles.leftPanel}>
      <div className={styles.scrollArea}>
        <StatBar />
        <div className={styles.bannerArea}>
          <div className={styles.bannerPlaceholder}>
            <span className={styles.bannerText}>贴图预留区域</span>
          </div>
        </div>
        <EventCards />
      </div>
      <ChatSection convId={convId} />
      {inputBubble}
    </aside>
  );
}

export default DashboardLeftPanel;
