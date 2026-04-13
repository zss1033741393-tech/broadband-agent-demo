import AlertOverlay from './AlertOverlay';
import styles from './RightArea.module.css';

function RightArea() {
  return (
    <div className={styles.rightArea}>
      {/* 4.1 顶部横幅 */}
      <div className={styles.topBanner}>
        <div className={styles.bannerPlaceholder}>
          <span className={styles.bannerText}>顶部横幅预留区域（1361 × 130）</span>
        </div>
      </div>

      {/* 4.2 地图区域 + 4.3 告警浮层 */}
      <div className={styles.mapArea}>
        {/* 地图底图占位 */}
        <div className={styles.mapPlaceholder}>
          <div className={styles.mapGrid} />
          <span className={styles.mapText}>地图底图预留区域</span>
        </div>

        {/* 告警浮层矩形，绝对定位叠加在地图上 */}
        <AlertOverlay />
      </div>
    </div>
  );
}

export default RightArea;
