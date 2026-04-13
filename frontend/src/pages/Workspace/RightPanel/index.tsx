import { useWorkspaceStore } from '@/store/workspaceStore';
import EmptyState from './EmptyState';
import ImageDisplay from './ImageDisplay';
import InsightDisplay from './InsightDisplay';
import styles from './RightPanel.module.css';
import type { InsightRenderData } from '@/types/render';

/** 根据图表数据密度决定占几列：pie 图或数据点少 → 1 列，数据密集 → 2 列 */
function getInsightSpan(data: InsightRenderData): 1 | 2 {
  const chart = data.charts[0];
  if (!chart) return 1;
  const option = chart.echartsOption;
  const series = (option.series ?? []) as { type?: string }[];
  if (series.some((s) => s.type === 'pie')) return 1;
  const xData = (option.xAxis as { data?: unknown[] } | undefined)?.data;
  if (Array.isArray(xData) && xData.length > 6) return 2;
  return 1;
}

function RightPanel() {
  const currentRenders = useWorkspaceStore((s) => s.currentRenders);

  if (currentRenders.length === 0) {
    return (
      <main className={styles.rightPanel}>
        <EmptyState />
      </main>
    );
  }

  return (
    <main className={styles.rightPanel}>
      <div className={styles.renderGrid}>
        {currentRenders.map((block, i) => {
          if (block.renderType === 'image') {
            return (
              <div key={i} className={styles.gridCell}>
                <ImageDisplay data={block.renderData} />
              </div>
            );
          }
          const span = getInsightSpan(block.renderData);
          return (
            <div
              key={i}
              className={styles.gridCell}
              style={span === 2 ? { gridColumn: '1 / -1' } : undefined}
            >
              <InsightDisplay data={block.renderData} />
            </div>
          );
        })}
      </div>
    </main>
  );
}

export default RightPanel;
