import emptyImg from '@/assets/images/empty-topology.png';
import styles from './EmptyState.module.css';

function EmptyState() {
  return (
    <div className={styles.empty}>
      <div className={styles.imagePlaceholder}>
        <img src={emptyImg} alt="网络拓扑" className={styles.topoImg} />
        <p className={styles.imageHint}>在左侧发起对话，分析结果将在此展示</p>
      </div>
    </div>
  );
}

export default EmptyState;
