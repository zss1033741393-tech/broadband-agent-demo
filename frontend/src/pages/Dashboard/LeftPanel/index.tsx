import StatBar from './StatBar';
import EventCards from './EventCards';
import AnalysisPanel from './AnalysisPanel';
import styles from './LeftPanel.module.css';

function DashboardLeftPanel() {
  return (
    <aside className={styles.leftPanel}>
      {/* 3.1 统计指标栏 */}
      <StatBar />

      {/* 3.2 贴图区 */}
      <div className={styles.bannerArea}>
        <div className={styles.bannerPlaceholder}>
          <span className={styles.bannerText}>贴图预留区域</span>
        </div>
      </div>

      {/* 3.3 人工带决策事件 */}
      <EventCards />

      {/* 3.4 网络级分析结论 */}
      <AnalysisPanel />
    </aside>
  );
}

export default DashboardLeftPanel;
