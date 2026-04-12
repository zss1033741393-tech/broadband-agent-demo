import { useState, useEffect, useRef } from 'react';
import { CheckCircleFilled, DownOutlined, LoadingOutlined } from '@ant-design/icons';
import styles from './ThinkingBlock.module.css';

/** 单个 \n 折叠成空格，双 \n 保留为段落分隔，避免 LLM 碎行渲染 */
function normalizeThinking(text: string): string {
  return text.replace(/([^\n])\n([^\n])/g, '$1 $2');
}

/** 取最后 n 条非空行 */
function lastLines(text: string, n: number): string {
  return text
    .split('\n')
    .filter((l) => l.trim().length > 0)
    .slice(-n)
    .join('\n');
}

/** streaming 期间每秒跳动的秒数 */
function useLiveSeconds(streaming: boolean, startedAt?: number): number {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!streaming || !startedAt) return;
    const tick = () => setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [streaming, startedAt]);
  return elapsed;
}

interface Props {
  content: string;
  startedAt?: number;   // 前端时间戳，用于 live 计时
  durationSec?: number; // 结束后的静态时长
  streaming?: boolean;
}

function ThinkingBlock({ content, startedAt, durationSec, streaming }: Props) {
  const [open, setOpen] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const liveSeconds = useLiveSeconds(!!streaming, startedAt);

  // 展开且流式时，自动滚到底部
  useEffect(() => {
    if (open && streaming && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [content, open, streaming]);

  const normalized = normalizeThinking(content);
  const preview = lastLines(normalized, 3);

  const label = streaming
    ? `正在深度思考... ${liveSeconds}s`
    : `已深度思考（${durationSec ?? 0}s）`;

  return (
    <div className={styles.block}>
      <button
        type="button"
        className={styles.head}
        onClick={() => setOpen((v) => !v)}
      >
        {streaming ? (
          <LoadingOutlined className={styles.iconLoading} spin />
        ) : (
          <CheckCircleFilled className={styles.iconDone} />
        )}
        <span>{label}</span>
        <DownOutlined
          className={`${styles.arrow} ${open ? styles.arrowOpen : ''}`}
        />
      </button>

      {!open && content && (
        <div className={styles.preview}>
          <div className={styles.previewFade} />
          <div className={styles.previewText}>{preview}</div>
        </div>
      )}

      {open && (
        <div className={styles.body} ref={bodyRef}>
          {normalized}
        </div>
      )}
    </div>
  );
}

export default ThinkingBlock;
