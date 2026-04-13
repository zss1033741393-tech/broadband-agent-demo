import styles from './AnalysisPanel.module.css';

function AnalysisPanel() {
  return (
    <div className={styles.section}>
      <div className={styles.sectionTitle}>网络级分析结论</div>
      <div className={styles.panel}>
        {/* 预留展示区，后续对接数据 */}
        <div className={styles.placeholder}>
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" className={styles.placeholderIcon}>
            <rect x="3" y="3" width="7" height="7" rx="1" stroke="#374151" strokeWidth="1.5" />
            <rect x="14" y="3" width="7" height="7" rx="1" stroke="#374151" strokeWidth="1.5" />
            <rect x="3" y="14" width="7" height="7" rx="1" stroke="#374151" strokeWidth="1.5" />
            <path d="M14 17.5h7M17.5 14v7" stroke="#374151" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          <span className={styles.placeholderText}>分析结论待接入</span>
        </div>
      </div>
    </div>
  );
}

export default AnalysisPanel;
