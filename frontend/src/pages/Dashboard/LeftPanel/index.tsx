import { useEffect, useRef, useState } from 'react';
import { useWorkspaceStore } from '@/store/workspaceStore';
import { useConversationStore } from '@/store/conversationStore';
import StatBar from './StatBar';
import EventCards from './EventCards';
import ChatSection from './ChatSection';
import MessageList from '@/pages/Workspace/LeftPanel/ChatView/MessageList';
import InputBubble from '@/pages/Workspace/LeftPanel/ChatView/InputBubble';
import styles from './LeftPanel.module.css';

interface Props {
  onViewReport: (content: string) => void;
}

/**
 * Dashboard 左侧面板：
 * - 默认模式：StatBar + Banner + EventCards + ChatSection + 输入框
 * - 发问后：底部 Sheet 从下方滑入，覆盖 EventCards 及以下内容
 * - 点击 Sheet 标题栏可收起
 */
function DashboardLeftPanel({ onViewReport }: Props) {
  const [convId, setConvId] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);

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
    setSheetOpen(true);
    sendMessage(content, deepThinking);
  };

  return (
    <aside className={styles.leftPanel}>
      {/* 默认布局——始终保留在 Sheet 背后 */}
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
      <div className={styles.inputArea}>
        <InputBubble
          inline
          disabled={!convId || isStreaming}
          disabledPlaceholder={!convId ? '初始化中...' : 'Agent 处理中...'}
          onSend={handleSend}
        />
      </div>

      {/* 对话 Sheet：从底部滑入 */}
      <div className={`${styles.sheet} ${sheetOpen ? styles.sheetOpen : ''}`}>
        {/* 标题栏：点击收起 */}
        <div className={styles.sheetHeader} onClick={() => setSheetOpen(false)}>
          <span className={styles.sheetTitle}>网络级分析</span>
          <span className={styles.sheetArrow}>↓</span>
        </div>

        {/* 消息列表 */}
        <div className={styles.sheetBody}>
          <MessageList
            messages={messages}
            loading={isLoading}
            isStreaming={isStreaming}
            onEditMessage={() => {}}
            onViewReport={onViewReport}
          />
        </div>

        {/* 跟进输入框 */}
        <div className={styles.sheetInput}>
          <InputBubble
            inline
            disabled={!convId || isStreaming}
            disabledPlaceholder={isStreaming ? 'Agent 处理中...' : ''}
            onSend={handleSend}
          />
        </div>
      </div>
    </aside>
  );
}

export default DashboardLeftPanel;
