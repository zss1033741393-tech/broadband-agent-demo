import { useEffect, useRef } from 'react';
import { Empty, Skeleton } from 'antd';
import type { Message } from '@/types/message';
import type { ChartItem } from '@/types/render';
import UserBubble from '../UserBubble';
import ThinkingBlock from '../ThinkingBlock';
import StepCard from '../StepCard';
import ConclusionCard from '../ConclusionCard';
import InsightPhasePanel from '../InsightPhasePanel';
import ErrorCard from '../ErrorCard';
import ReportFloatBtn from '@/components/ReportFloatBtn';
import styles from './MessageList.module.css';

interface Props {
  messages: Message[];
  loading: boolean;
  isStreaming: boolean;
  onEditMessage: (content: string) => void;
  onViewReport?: (content: string, charts: ChartItem[]) => void;
}

function MessageList({ messages, loading, isStreaming, onEditMessage, onViewReport }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages, isStreaming]);

  if (loading) {
    return (
      <div className={styles.scroll}>
        <div className={styles.loading}>
          <Skeleton active paragraph={{ rows: 2 }} />
          <Skeleton active paragraph={{ rows: 3 }} />
        </div>
      </div>
    );
  }

  if (messages.length === 0) {
    return (
      <div className={styles.scroll}>
        <div className={styles.empty}>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={<span style={{ color: '#6b7280' }}>开始你的第一句提问</span>}
          />
        </div>
      </div>
    );
  }

  return (
    <div className={styles.scroll} ref={scrollRef}>
      <div className={styles.list}>
        {messages.map((msg) => {
          if (msg.role === 'user') {
            return (
              <UserBubble
                key={msg.id}
                content={msg.content}
                onEdit={onEditMessage}
              />
            );
          }

          // assistant：按 blocks 顺序渲染，保留流到达顺序
          const blocks = msg.blocks ?? [];
          const assistantMessages = messages.filter((m) => m.role === 'assistant');
          const isLastAssistant = msg === assistantMessages[assistantMessages.length - 1];
          const reportBlock = isLastAssistant
            ? [...blocks].reverse().find((b) => b.type === 'report_ready')
            : undefined;
          return (
            <div key={msg.id} className={styles.assistantGroup}>
              {blocks.map((block, i) => {
                if (block.type === 'thinking') {
                  const isHistory = block.startedAt === 0;
                  const durationSec = isHistory
                    ? msg.thinkingDurationSec
                    : block.endedAt
                      ? Math.round((block.endedAt - block.startedAt) / 1000)
                      : undefined;
                  return (
                    <ThinkingBlock
                      key={`thinking-${i}`}
                      content={block.content}
                      startedAt={isHistory ? undefined : block.startedAt}
                      durationSec={durationSec}
                      streaming={!isHistory && !block.endedAt && !!msg.streaming}
                    />
                  );
                }
                if (block.type === 'step') {
                  const step = (msg.steps ?? []).find((s) => s.stepId === block.stepId);
                  return step ? <StepCard key={step.stepId} step={step} streaming={msg.streaming} /> : null;
                }
                if (block.type === 'text') {
                  return (
                    <ConclusionCard
                      key={`text-${i}`}
                      content={block.content}
                      streaming={msg.streaming}
                    />
                  );
                }
                if (block.type === 'report_ready') {
                  return null;
                }
                return null;
              })}
              {/* phase 进度卡片始终渲染在 assistantGroup 最底部 */}
              {msg.insightState && <InsightPhasePanel state={msg.insightState} />}
              {msg.error && <ErrorCard message={msg.error} />}
              {/* 最后一条 assistant 消息底部固定报告按钮 */}
              {reportBlock && reportBlock.type === 'report_ready' && onViewReport && (
                <ReportFloatBtn
                  content={reportBlock.content}
                  charts={reportBlock.charts}
                  onView={onViewReport}
                />
              )}
            </div>
          );
        })}
        <div className={styles.bottomSpacer} />
      </div>
    </div>
  );
}

export default MessageList;
