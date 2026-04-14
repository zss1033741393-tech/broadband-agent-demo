import AlertOverlay from './AlertOverlay';
import ReportView from './ReportView';
import styles from './RightArea.module.css';

interface Props {
  view: 'map' | 'report';
  reportContent: string;
  onBack: () => void;
}

function RightArea({ view, reportContent, onBack }: Props) {
  return (
    <div className={styles.rightArea}>
      {/* 4.1 顶部横幅 */}
      <div className={styles.topBanner}>
        <img src="/images/top-banner.png" alt="顶部横幅" className={styles.topBannerImg} />
      </div>

      {view === 'report' ? (
        <ReportView content={reportContent} onBack={onBack} />
      ) : (
        /* 4.2 地图区域 + 4.3 告警浮层 */
        <div className={styles.mapArea}>
          <img src="/images/map-bg.png" alt="区域地图" className={styles.mapBgImg} />
          <AlertOverlay />
        </div>
      )}
    </div>
  );
}

export default RightArea;
