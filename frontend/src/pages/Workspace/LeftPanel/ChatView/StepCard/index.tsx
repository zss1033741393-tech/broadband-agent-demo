import { useState, useRef, useEffect } from 'react';
import { CheckCircleFilled, RightOutlined, LoadingOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import type { Step, StepItem } from '@/types/message';
import styles from './StepCard.module.css';

function normalizeThinking(text: string): string {
  return text.replace(/([^\n])\n([^\n])/g, '$1 $2');
}

function lastLines(text: string, n: number): string {
  return text
    .split('\n')
    .filter((l) => l.trim().length > 0)
    .slice(-n)
    .join('\n');
}

function useLiveSeconds(streaming: boolean, startedAt: number): number {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!streaming) return;
    const tick = () => setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [streaming, startedAt]);
  return elapsed;
}

function formatDuration(ms: number) {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

interface ThinkingItemProps {
  content: string;
  startedAt: number;
  endedAt?: number;
  streaming?: boolean;
}

function InlineThinking({ content, startedAt, endedAt, streaming }: ThinkingItemProps) {
  const [open, setOpen] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const isStreaming = !!streaming && !endedAt;
  const liveSeconds = useLiveSeconds(isStreaming, startedAt);

  useEffect(() => {
    if (open && isStreaming && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [content, open, isStreaming]);

  const durationSec = endedAt ? Math.round((endedAt - startedAt) / 1000) : undefined;
  const normalized = normalizeThinking(content);
  const preview = lastLines(normalized, 3);

  const label = isStreaming
    ? `思考中... ${liveSeconds}s`
    : `思考（${durationSec ?? 0}s）`;

  return (
    <div className={styles.thinkingItem}>
      <button
        type="button"
        className={styles.thinkingToggle}
        onClick={() => setOpen((v) => !v)}
      >
        {isStreaming
          ? <LoadingOutlined className={styles.thinkingIconLoading} spin />
          : <span className={styles.thinkingDot} />
        }
        <span className={styles.thinkingLabel}>{label}</span>
        <RightOutlined className={`${styles.thinkingArrow} ${open ? styles.thinkingArrowOpen : ''}`} />
      </button>

      {!open && preview && (
        <div className={styles.thinkingPreview}>
          <div className={styles.thinkingPreviewFade} />
          <div className={styles.thinkingPreviewText}>{preview}</div>
        </div>
      )}

      {open && (
        <div className={styles.thinkingBody} ref={bodyRef}>
          {normalized}
        </div>
      )}
    </div>
  );
}

interface Props {
  step: Step;
  defaultExpanded?: boolean;
  streaming?: boolean;
}

function StepCard({ step, defaultExpanded = true, streaming }: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <div className={`${styles.card} ${expanded ? styles.expanded : ''}`}>
      <button
        type="button"
        className={styles.head}
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        {step.completed || !streaming
          ? <CheckCircleFilled className={styles.statusIcon} />
          : <LoadingOutlined className={styles.statusIconLoading} spin />
        }
        <span className={styles.title}>{step.title}</span>
        <span className={styles.count}>{step.subSteps.length} 步</span>
        <RightOutlined className={`${styles.arrow} ${expanded ? styles.arrowOpen : ''}`} />
      </button>

      {expanded && (
        <div className={styles.body}>
          {(step.items ?? []).length === 0 ? (
            <div className={styles.placeholder}>暂无内容</div>
          ) : (
            <div className={styles.itemList}>
              {step.items.map((item: StepItem, i: number) => {
                if (item.type === 'thinking') {
                  return (
                    <InlineThinking
                      key={`thinking-${i}`}
                      content={item.content}
                      startedAt={item.startedAt}
                      endedAt={item.endedAt}
                      streaming={streaming}
                    />
                  );
                }
                if (item.type === 'text') {
                  return (
                    <div key={`text-${i}`} className={styles.inlineText}>
                      {item.content}
                    </div>
                  );
                }
                const sub = item.data;
                const isLast = i === step.items.length - 1;
                return (
                  <div key={sub.subStepId} className={styles.tlItem}>
                    <span className={`${styles.dot} ${isLast ? styles.dotLast : ''}`} />
                    <div className={styles.tlContent}>
                      <div className={styles.tlHeader}>
                        <span className={styles.tlName}>{sub.name}</span>
                        <span className={styles.tlTime}>
                          {dayjs(sub.completedAt).format('HH:mm:ss')} · {formatDuration(sub.durationMs)}
                        </span>
                      </div>
                      {/* 调用信息 */}
                      {sub.scriptPath && (
                        <div className={styles.tlCall}>
                          <span className={styles.tlCallLabel}>调用</span>
                          <code className={styles.tlCallScript}>{sub.scriptPath}</code>
                          {sub.callArgs && sub.callArgs.length > 0 && (
                            <span className={styles.tlCallArgs}>
                              {sub.callArgs.map((a, ai) => (
                                <code key={ai} className={styles.tlCallArg}>{a}</code>
                              ))}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default StepCard;
