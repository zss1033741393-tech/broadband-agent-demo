import { useCallback, useEffect, useRef, useState } from 'react';
import { useWorkspaceStore } from '@/store/workspaceStore';
import { useConversationStore } from '@/store/conversationStore';
import StatBar from './StatBar';
import EventCards from './EventCards';
import ChatSection from './ChatSection';
import MessageList from '@/pages/Workspace/LeftPanel/ChatView/MessageList';
import InputBubble from '@/pages/Workspace/LeftPanel/ChatView/InputBubble';
import ReportFloatBtn from '@/components/ReportFloatBtn';
import styles from './LeftPanel.module.css';

import type { ChartItem } from '@/types/render';

interface Props {
  onViewReport: (content: string, charts: ChartItem[]) => void;
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
  const [sheetHeight, setSheetHeight] = useState(700);
  const [resizing, setResizing] = useState(false);
  const contentAreaRef = useRef<HTMLDivElement>(null);
  const dragStartY = useRef(0);
  const dragStartHeight = useRef(0);

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

  // 计算 sheet 的 transform（hidden / collapsed / expanded）
  const sheetTranslateY = sheetOpen
    ? 0
    : messages.length > 0
      ? sheetHeight - 36   // 收起：露出 36px 标题栏
      : sheetHeight;        // 完全隐藏

  const sheetStyle: React.CSSProperties = {
    height: sheetHeight,
    transform: `translateY(${sheetTranslateY}px)`,
  };

  const sheetClass = [styles.sheet, resizing ? styles.noTransition : ''].join(' ');

  // 拖拽手柄 mousedown
  const onDragMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation(); // 不触发 header 的 onClick
    setResizing(true);
    dragStartY.current = e.clientY;
    dragStartHeight.current = sheetHeight;

    const onMouseMove = (ev: MouseEvent) => {
      const delta = dragStartY.current - ev.clientY; // 向上拖 delta > 0 → 变高
      const maxH = contentAreaRef.current ? contentAreaRef.current.clientHeight : 900;
      const next = Math.min(maxH, Math.max(80, dragStartHeight.current + delta));
      setSheetHeight(next);
      // 拖到很小时自动收起
      if (next <= 80 && sheetOpen) setSheetOpen(false);
      else if (next > 80 && !sheetOpen) setSheetOpen(true);
    };

    const onMouseUp = () => {
      setResizing(false);
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    document.body.style.cursor = 'ns-resize';
    document.body.style.userSelect = 'none';
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sheetHeight, sheetOpen]);

  return (
    <aside className={styles.leftPanel}>
      {/* contentArea：sheet 的定位参照容器，撑满输入框以上的全部空间 */}
      <div className={styles.contentArea} ref={contentAreaRef}>
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
        <div className={sheetClass} style={sheetStyle}>
          {/* 拖拽手柄：按住上下拖动调整高度 */}
          <div className={styles.dragHandle} onMouseDown={onDragMouseDown} />
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
            />
          </div>
        </div>
      </div>

      {/* 报告就绪时的固定悬浮按钮，紧贴输入框上方 */}
      {(() => {
        const allBlocks = messages.flatMap((m) => m.blocks ?? []);
        const reportBlock = [...allBlocks].reverse().find((b) => b.type === 'report_ready');
        if (!reportBlock || reportBlock.type !== 'report_ready') return null;
        return (
          <ReportFloatBtn
            content={reportBlock.content}
            charts={reportBlock.charts}
            onView={onViewReport}
          />
        );
      })()}

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
