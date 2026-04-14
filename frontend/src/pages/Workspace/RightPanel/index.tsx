import { useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useWorkspaceStore } from '@/store/workspaceStore';
import EmptyState from './EmptyState';
import ImageDisplay from './ImageDisplay';
import InsightDisplay from './InsightDisplay';
import ReportView from '@/pages/Dashboard/RightArea/ReportView';
import styles from './RightPanel.module.css';
import type { RenderBlock } from '@/types/render';
import type { InsightState } from '@/types/insight';

const SOLO_THRESHOLD = 0.70;

function computeWidth(block: RenderBlock): number {
  if (block.renderType === 'image') return 0.5;
  const chart = block.renderData.charts[0];
  if (!chart) return 0.5;
  const series = (chart.echartsOption.series ?? []) as { type?: string; data?: unknown[] }[];
  const nonPieSeries = series.filter((s) => s.type !== 'pie');
  if (nonPieSeries.length === 0) return 0.35;

  const xData = (chart.echartsOption.xAxis as { data?: unknown[] } | undefined)?.data;
  const yData = (chart.echartsOption.yAxis as { data?: unknown[]; type?: string } | undefined);
  const categoryData = Array.isArray(xData) ? xData
    : (yData?.type === 'category' && Array.isArray(yData?.data)) ? yData.data
    : [];
  const xCount = categoryData.length;
  const seriesCount = nonPieSeries.length || 1;
  const effectiveCount = xCount * seriesCount;
  if (effectiveCount === 0) return 0.5;

  const hasPie = series.some((s) => s.type === 'pie');
  const base = Math.min(0.75, Math.max(0.40, effectiveCount * 0.015));
  return hasPie ? Math.min(0.75, base + 0.15) : base;
}

function getReport(block: RenderBlock): string | undefined {
  return block.renderType === 'insight' && block.renderData.markdownReport?.trim()
    ? block.renderData.markdownReport
    : undefined;
}

function getPhaseId(block: RenderBlock): number | undefined {
  if (block.renderType === 'image') return undefined;
  return block.renderData.charts[0]?.phaseId;
}

type LayoutRow =
  | { kind: 'phase_title'; phaseId: number; phaseName: string }
  | { kind: 'single'; block: RenderBlock; solo: boolean; report?: string }
  | { kind: 'pair'; left: RenderBlock; right: RenderBlock; leftPct: number; report?: string };

function computeRows(renders: RenderBlock[], insightState?: InsightState): LayoutRow[] {
  const rows: LayoutRow[] = [];
  const seenPhases = new Set<number>();

  const getPhaseName = (phaseId: number) => {
    const phase = insightState?.phases.find((p) => p.phaseId === phaseId);
    return phase?.name ?? `阶段 ${phaseId}`;
  };

  for (const block of renders) {
    const phaseId = getPhaseId(block);

    // 新 phase 首次出现：插入标题卡，并强制断开上一行配对
    if (phaseId !== undefined && !seenPhases.has(phaseId)) {
      seenPhases.add(phaseId);
      rows.push({ kind: 'phase_title', phaseId, phaseName: getPhaseName(phaseId) });
    }

    const w = computeWidth(block);
    const report = getReport(block);
    const isSolo = w >= SOLO_THRESHOLD;
    const lastRow = rows[rows.length - 1];

    // 可配对条件：上一行是 single，同 phase，无 report，未超阈值
    const lastIsSingle = lastRow?.kind === 'single';
    const samePhase = lastIsSingle && getPhaseId((lastRow as { block: RenderBlock }).block) === phaseId;

    if (
      !isSolo &&
      lastIsSingle &&
      samePhase &&
      !(lastRow as { report?: string }).report &&
      computeWidth((lastRow as { block: RenderBlock }).block) < SOLO_THRESHOLD
    ) {
      const leftW = computeWidth((lastRow as { block: RenderBlock }).block);
      const total = leftW + w;
      const leftPct = Math.round((leftW / total) * 100);
      rows[rows.length - 1] = {
        kind: 'pair',
        left: (lastRow as { block: RenderBlock }).block,
        right: block,
        leftPct,
        report,
      };
    } else {
      rows.push({ kind: 'single', block, solo: isSolo, report });
    }
  }

  return rows;
}

function renderBlock(block: RenderBlock) {
  if (block.renderType === 'image') return <ImageDisplay data={block.renderData} />;
  return <InsightDisplay data={block.renderData} />;
}

interface Props {
  fromEventCard: boolean;
}

function RightPanel({ fromEventCard }: Props) {
  const currentRenders = useWorkspaceStore((s) => s.currentRenders);
  const leftView = useWorkspaceStore((s) => s.leftView);
  const activeId = useWorkspaceStore((s) => s.activeConversationId);
  const messages = useWorkspaceStore((s) => s.messagesByConvId[activeId ?? ''] ?? []);
  const activeReport = useWorkspaceStore((s) => s.activeReport);
  const setActiveReport = useWorkspaceStore((s) => s.setActiveReport);
  const bottomRef = useRef<HTMLDivElement>(null);

  // 取最新 assistant 消息的 insightState 用于 phase 名查找
  const insightState = [...messages].reverse().find(
    (m) => m.role === 'assistant' && m.insightState
  )?.insightState;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [currentRenders.length]);

  // 会话列表状态：右侧完全空白
  if (leftView === 'list') {
    return <main className={styles.rightPanel} />;
  }

  // 报告视图：覆盖在右侧画布上
  if (activeReport) {
    return (
      <main className={styles.rightPanel}>
        <ReportView
          content={activeReport.content}
          charts={activeReport.charts}
          onBack={() => setActiveReport(null)}
        />
      </main>
    );
  }

  // 无渲染内容：仅事件卡片入口显示 EmptyState，其他情况空白
  if (currentRenders.length === 0) {
    return (
      <main className={styles.rightPanel}>
        {fromEventCard && <EmptyState />}
      </main>
    );
  }

  const rows = computeRows(currentRenders, insightState);

  return (
    <main className={styles.rightPanel}>
      {rows.map((row, i) => {
        if (row.kind === 'phase_title') {
          return (
            <div key={`title-${row.phaseId}`} className={styles.phaseTitle}>
              <span className={styles.phaseTitleText}>
                Phase {row.phaseId}
                <span className={styles.phaseTitleSep}>·</span>
                {row.phaseName}
              </span>
            </div>
          );
        }

        return (
          <div key={i} className={styles.rowWrap}>
            <div className={styles.rowItems}>
              {row.kind === 'single' ? (
                <div style={{ width: row.solo ? '100%' : '50%' }}>
                  {renderBlock(row.block)}
                </div>
              ) : (
                <>
                  <div style={{ width: `${row.leftPct}%`, flexShrink: 0 }}>
                    {renderBlock(row.left)}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    {renderBlock(row.right)}
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
        );
      })}
      <div ref={bottomRef} />
    </main>
  );
}

export default RightPanel;
