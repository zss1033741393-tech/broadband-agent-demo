import { useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useWorkspaceStore } from '@/store/workspaceStore';
import EmptyState from './EmptyState';
import ImageDisplay from './ImageDisplay';
import InsightDisplay from './InsightDisplay';
import styles from './RightPanel.module.css';
import type { RenderBlock } from '@/types/render';

const SOLO_THRESHOLD = 0.70; // 自然宽度超过此值则独占整行

/** 根据数据量线性计算自然宽度（0~1） */
function computeWidth(block: RenderBlock): number {
  if (block.renderType === 'image') return 0.5;
  const chart = block.renderData.charts[0];
  if (!chart) return 0.5;
  const series = (chart.echartsOption.series ?? []) as { type?: string; data?: unknown[] }[];
  if (series.some((s) => s.type === 'pie')) return 0.35;

  const xData = (chart.echartsOption.xAxis as { data?: unknown[] } | undefined)?.data;
  const xCount = Array.isArray(xData) ? xData.length : 0;

  // 非 pie 的 series 数量（分组柱状图每个 x 有多根柱子）
  const seriesCount = series.filter((s) => s.type !== 'pie').length || 1;

  // 有效密度 = x 轴数 × series 数
  const effectiveCount = xCount * seriesCount;
  if (effectiveCount === 0) return 0.5;

  // clamp(40%, effectiveCount * 1.5%, 75%)
  return Math.min(0.75, Math.max(0.40, effectiveCount * 0.015));
}

function getReport(block: RenderBlock): string | undefined {
  return block.renderType === 'insight' && block.renderData.markdownReport?.trim()
    ? block.renderData.markdownReport
    : undefined;
}

type Row =
  | { kind: 'single'; block: RenderBlock; report?: string }
  | { kind: 'pair'; left: RenderBlock; right: RenderBlock; leftPct: number; report?: string };

/** 贪心行分配：配对时按双方自然宽度归一化，动态决定各自占比 */
function computeRows(renders: RenderBlock[]): Row[] {
  const rows: Row[] = [];

  for (const block of renders) {
    const w = computeWidth(block);
    const report = getReport(block);
    const lastRow = rows[rows.length - 1];

    // 自然宽度超过阈值 → 独占整行
    const isSolo = w >= SOLO_THRESHOLD;

    // 上一行是等待配对的单图（无 report、未超阈值）→ 配对
    if (
      !isSolo &&
      lastRow?.kind === 'single' &&
      !lastRow.report &&
      computeWidth(lastRow.block) < SOLO_THRESHOLD
    ) {
      const leftW = computeWidth(lastRow.block);
      const total = leftW + w;
      // 按自然宽度比例归一化，决定左图百分比
      const leftPct = Math.round((leftW / total) * 100);
      rows[rows.length - 1] = {
        kind: 'pair',
        left: lastRow.block,
        right: block,
        leftPct,
        report,
      };
    } else {
      rows.push({ kind: 'single', block, report });
    }
  }

  return rows;
}

function RightPanel() {
  const currentRenders = useWorkspaceStore((s) => s.currentRenders);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [currentRenders.length]);

  if (currentRenders.length === 0) {
    return (
      <main className={styles.rightPanel}>
        <EmptyState />
      </main>
    );
  }

  const rows = computeRows(currentRenders);

  return (
    <main className={styles.rightPanel}>
      {rows.map((row, i) => (
        <div key={i} className={styles.rowWrap}>
          <div className={styles.rowItems}>
            {row.kind === 'single' ? (
              <div style={{ width: '100%' }}>
                {row.block.renderType === 'image'
                  ? <ImageDisplay data={row.block.renderData} />
                  : <InsightDisplay data={row.block.renderData} />}
              </div>
            ) : (
              <>
                <div style={{ width: `${row.leftPct}%`, flexShrink: 0 }}>
                  {row.left.renderType === 'image'
                    ? <ImageDisplay data={row.left.renderData} />
                    : <InsightDisplay data={row.left.renderData} />}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  {row.right.renderType === 'image'
                    ? <ImageDisplay data={row.right.renderData} />
                    : <InsightDisplay data={row.right.renderData} />}
                </div>
              </>
            )}
          </div>

          {row.report && (
            <div className={styles.reportRow}>
              <div className={styles.reportInner}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{row.report}</ReactMarkdown>
              </div>
            </div>
          )}
        </div>
      ))}
      <div ref={bottomRef} />
    </main>
  );
}

export default RightPanel;
