import { useState } from 'react';
import AlertOverlay from './AlertOverlay';
import ReportView from './ReportView';
import styles from './RightArea.module.css';
import type { ChartItem } from '@/types/render';

interface Props {
  view: 'map' | 'report';
  reportContent: string;
  reportCharts: ChartItem[];
  onBack: () => void;
}

const MIN_ZOOM = 0.4;
const MAX_ZOOM = 3.0;
const STEP = 0.15;

function RightArea({ view, reportContent, reportCharts, onBack }: Props) {
  const [zoom, setZoom] = useState(1);

  const zoomIn  = () => setZoom((z) => Math.min(MAX_ZOOM, parseFloat((z + STEP).toFixed(2))));
  const zoomOut = () => setZoom((z) => Math.max(MIN_ZOOM, parseFloat((z - STEP).toFixed(2))));

  return (
    <div className={styles.rightArea}>
      {/* 4.1 顶部横幅 */}
      <div className={styles.topBanner}>
        <img src="/images/top-banner.png" alt="顶部横幅" className={styles.topBannerImg} />
      </div>

      {view === 'report' ? (
        <ReportView content={reportContent} charts={reportCharts} onBack={onBack} />
      ) : (
        /* 4.2 地图区域 + 4.3 告警浮层 */
        <div className={styles.mapArea}>
          {/* mapCanvas：图片 + 标签整体缩放，保持相对位置固定 */}
          <div
            className={styles.mapCanvas}
            style={{ transform: `scale(${zoom})` }}
          >
            <img src="/images/map-bg.png" alt="区域地图" className={styles.mapBgImg} />
            <AlertOverlay />
          </div>

          {/* 缩放控件：固定在地图右下角，不随 canvas 缩放 */}
          <div className={styles.zoomControls}>
            <button
              className={styles.zoomBtn}
              onClick={zoomIn}
              disabled={zoom >= MAX_ZOOM}
              aria-label="放大"
            >+</button>
            <span className={styles.zoomLabel}>{Math.round(zoom * 100)}%</span>
            <button
              className={styles.zoomBtn}
              onClick={zoomOut}
              disabled={zoom <= MIN_ZOOM}
              aria-label="缩小"
            >−</button>
          </div>
        </div>
      )}
    </div>
  );
}

export default RightArea;
