import { useEffect, useRef } from 'react';
import { Empty, Skeleton } from 'antd';
import type { Message } from '@/types/message';
import UserBubble from '../UserBubble';
import ThinkingBlock from '../ThinkingBlock';
import StepCard from '../StepCard';
import ConclusionCard from '../ConclusionCard';
import ErrorCard from '../ErrorCard';
import styles from './MessageList.module.css';

interface Props {
  messages: Message[];
  loading: boolean;
  isStreaming: boolean;
  onEditMessage: (content: string) => void;
}

function MessageList({ messages, loading, isStreaming, onEditMessage }: Props) {
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
                  // 最后一个 text block 才挂 insightState
                  const isLastText = blocks.slice(i + 1).every((b) => b.type !== 'text');
                  return (
                    <ConclusionCard
                      key={`text-${i}`}
                      content={block.content}
                      streaming={msg.streaming}
                      insightState={isLastText ? msg.insightState : undefined}
                    />
                  );
                }
                return null;
              })}
              {/* 无 text block 但有 insightState 时单独渲染进度面板 */}
              {msg.insightState && !blocks.some((b) => b.type === 'text') && (
                <ConclusionCard key="insight-only" content="" insightState={msg.insightState} />
              )}
              {msg.error && <ErrorCard message={msg.error} />}
            </div>
          );
        })}
        <div className={styles.bottomSpacer} />
      </div>
    </div>
  );
}

export default MessageList;
