import { useEffect, useRef, useCallback } from 'react';
import { Empty, Skeleton } from 'antd';
import type { Message } from '@/types/message';
import type { ChartItem } from '@/types/render';
import type { PlanGroup } from '@/api/protectionPlan';
import UserBubble from '../UserBubble';
import ThinkingBlock from '../ThinkingBlock';
import StepCard from '../StepCard';
import ConclusionCard from '../ConclusionCard';
import ProtectionPlanCard from '../ProtectionPlanCard';
import InsightPhasePanel from '../InsightPhasePanel';
import ErrorCard from '../ErrorCard';
import ReportFloatBtn from '@/components/ReportFloatBtn';
import ExperienceAssuranceCard from '../ExperienceAssuranceCard';
import ProtectionPlanCard from '../ProtectionPlanCard';
import styles from './MessageList.module.css';

interface Props {
  messages: Message[];
  loading: boolean;
  isStreaming: boolean;
  planGroups?: PlanGroup[];
  onEditMessage: (content: string) => void;
  onViewReport?: (content: string, charts: ChartItem[]) => void;
  /** 为 true 时不在消息流中渲染 InsightPhasePanel（由外层面板负责渲染） */
  hideInsightPanel?: boolean;
}

// 距底部多少 px 以内视为"在底部"
const NEAR_BOTTOM_THRESHOLD = 80;

function MessageList({ messages, loading, isStreaming, onEditMessage, onViewReport, hideInsightPanel }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  // 用户是否主动向上滚动离开了底部
  const userScrolledUpRef = useRef(false);
  // 记录消息数量，用于判断是否新增了消息（切换会话 / 发送新消息 → 强制回底）
  const prevMsgCountRef = useRef(messages.length);

  const isNearBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_THRESHOLD;
  }, []);

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, []);

  // onScroll prop 直接绑定，避免 useEffect 时机问题（初始空状态下 scrollRef 为 null）
  const handleScroll = useCallback(() => {
    userScrolledUpRef.current = !isNearBottom();
  }, [isNearBottom]);

  useEffect(() => {
    const msgCount = messages.length;
    const prevCount = prevMsgCountRef.current;
    prevMsgCountRef.current = msgCount;

    // 新增了消息（用户发送 / 切换会话）→ 无条件滚到底并重置标志
    if (msgCount > prevCount) {
      userScrolledUpRef.current = false;
      scrollToBottom();
      return;
    }

    // 流式更新中：用户没有向上滚 → 持续跟随底部
    if (isStreaming && !userScrolledUpRef.current) {
      scrollToBottom();
    }
  }, [messages, isStreaming, scrollToBottom]);

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
    <div className={styles.scroll} ref={scrollRef} onScroll={handleScroll}>
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
                if (block.type === 'protection_plan') {
                  return planGroups?.length
                    ? <ProtectionPlanCard key="plan-card" groups={planGroups} />
                    : null;
                }
                if (block.type === 'report_ready') {
                  return null;
                }
                if (block.type === 'experience_assurance') {
                  return <ExperienceAssuranceCard key={`ea-${i}`} data={block.data} />;
                }
                if (block.type === 'protection_plan') {
                  return <ProtectionPlanCard key={`pp-${i}`} />;
                }
                return null;
              })}
              {/* phase 进度卡片始终渲染在 assistantGroup 最底部 */}
              {msg.insightState && !hideInsightPanel && <InsightPhasePanel state={msg.insightState} />}
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
