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
 * - 输入框始终固定在底部
 * - 发问后：Sheet（header + MessageList）从输入框上方滑入
 * - 点击 Sheet 标题栏可收起/展开，收起后紧贴输入框上侧
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
  const updateTitle = useConversationStore((s) => s.updateTitle);

  const initiated = useRef(false);

  useEffect(() => {
    if (initiated.current) return;
    initiated.current = true;
    (async () => {
      try {
        const conv = await createConversation('网络级入口');
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
    if (messages.length === 0) {
      updateTitle(convId, `网络级入口-${content.slice(0, 20)}`);
    }
    sendMessage(content, deepThinking);
  };

  const sheetClass = [
    styles.sheet,
    messages.length > 0 && !sheetOpen ? styles.sheetCollapsed : '',
    sheetOpen ? styles.sheetExpanded : '',
  ].join(' ');

  return (
    <aside className={styles.leftPanel}>
      {/* contentArea：sheet 的定位参照容器，撑满输入框以上的全部空间 */}
      <div className={styles.contentArea}>
        <div className={styles.scrollArea}>
          <StatBar />
          <div className={styles.bannerArea}>
            <img
              src="/images/dashboard-banner.png"
              alt="区域概况"
              className={styles.bannerImg}
            />
          </div>
          <EventCards />
        </div>
        <ChatSection convId={convId} />

        {/* 对话 Sheet：仅含 header + 消息列表，无自带输入框 */}
        <div className={sheetClass}>
          <div
            className={styles.sheetHeader}
            onClick={() => setSheetOpen((prev) => !prev)}
          >
            <div className={styles.sheetTitleRow}>
              <span className={styles.sheetTitle}>网络级分析</span>
              {isStreaming && (
                <span className={styles.loadingDots}>
                  <span /><span /><span />
                </span>
              )}
            </div>
            <span className={`${styles.chevron} ${sheetOpen ? styles.chevronOpen : styles.chevronClosed}`} />
          </div>

          <div className={styles.sheetBody}>
            <MessageList
              messages={messages}
              loading={isLoading}
              isStreaming={isStreaming}
              onEditMessage={() => {}}
              onViewReport={onViewReport}
            />
          </div>
        </div>
      </div>

      {/* 输入框：始终固定在面板底部，位置永远不变 */}
      <div className={styles.inputArea}>
        <InputBubble
          inline
          disabled={!convId || isStreaming}
          disabledPlaceholder={!convId ? '初始化中...' : 'Agent 处理中...'}
          onSend={handleSend}
        />
      </div>
    </aside>
  );
}

export default DashboardLeftPanel;
