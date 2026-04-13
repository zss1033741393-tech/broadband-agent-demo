import styles from './EmptyState.module.css';

function EmptyState() {
  return (
    <div className={styles.empty}>
      {/* 预设图片占位，后续替换为真实图片资源 */}
      <div className={styles.imagePlaceholder}>
        <svg width="80" height="80" viewBox="0 0 120 120" fill="none" className={styles.placeholderSvg}>
          {/* 网络拓扑示意图 */}
          <circle cx="60" cy="28" r="10" stroke="#1f2937" strokeWidth="2" />
          <circle cx="28" cy="72" r="10" stroke="#1f2937" strokeWidth="2" />
          <circle cx="60" cy="72" r="10" stroke="#1f2937" strokeWidth="2" />
          <circle cx="92" cy="72" r="10" stroke="#1f2937" strokeWidth="2" />
          <line x1="60" y1="38" x2="28" y2="62" stroke="#1f2937" strokeWidth="1.5" />
          <line x1="60" y1="38" x2="60" y2="62" stroke="#1f2937" strokeWidth="1.5" />
          <line x1="60" y1="38" x2="92" y2="62" stroke="#1f2937" strokeWidth="1.5" />
          <circle cx="60" cy="28" r="6" fill="#1677ff" fillOpacity="0.3" />
          <circle cx="60" cy="28" r="3" fill="#1677ff" />
          <circle cx="28" cy="72" r="3" fill="#30363d" />
          <circle cx="60" cy="72" r="3" fill="#30363d" />
          <circle cx="92" cy="72" r="3" fill="#30363d" />
          {/* 信号波纹 */}
          <circle cx="60" cy="28" r="16" stroke="#1677ff" strokeWidth="1" strokeOpacity="0.15" strokeDasharray="3 3" />
          <circle cx="60" cy="28" r="22" stroke="#1677ff" strokeWidth="1" strokeOpacity="0.08" strokeDasharray="3 3" />
        </svg>
        <p className={styles.imageHint}>在左侧发起对话，分析结果将在此展示</p>
      </div>
    </div>
  );
}

export default EmptyState;
