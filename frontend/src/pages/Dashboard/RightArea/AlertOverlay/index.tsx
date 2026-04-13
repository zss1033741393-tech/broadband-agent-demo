import styles from './AlertOverlay.module.css';

interface AlertTag {
  id: string;
  text: string;
  top: string;
  left: string;
  level: 'red' | 'orange' | 'yellow';
}

const ALERTS: AlertTag[] = [
  { id: 'a1', text: '120个用户出现体验劣化，正在处置中', top: '12%', left: '8%', level: 'red' },
  { id: 'a2', text: 'PON口 2/0/5 CEI评分持续下降', top: '28%', left: '55%', level: 'red' },
  { id: 'a3', text: 'Wi-Fi干扰告警，影响35个终端', top: '18%', left: '30%', level: 'orange' },
  { id: 'a4', text: '光功率异常，3个 ONU 离线', top: '45%', left: '70%', level: 'red' },
  { id: 'a5', text: '业务时延超标，峰值 280ms', top: '60%', left: '15%', level: 'orange' },
  { id: 'a6', text: '45个用户上行速率低于阈值', top: '52%', left: '42%', level: 'yellow' },
  { id: 'a7', text: '网关重启异常，远程闭环待执行', top: '75%', left: '62%', level: 'red' },
  { id: 'a8', text: '直播卡顿投诉，2起待处理', top: '70%', left: '25%', level: 'orange' },
];

const LEVEL_COLORS = {
  red: '#ef4444',
  orange: '#f97316',
  yellow: '#eab308',
};

function AlertOverlay() {
  return (
    <>
      {ALERTS.map((alert) => (
        <div
          key={alert.id}
          className={styles.tag}
          style={{ top: alert.top, left: alert.left }}
          title={alert.text}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" className={styles.tagIcon}>
            <circle cx="12" cy="12" r="10" fill={LEVEL_COLORS[alert.level]} fillOpacity="0.2" />
            <circle cx="12" cy="12" r="4" fill={LEVEL_COLORS[alert.level]} />
          </svg>
          <span className={styles.tagText}>{alert.text}</span>
        </div>
      ))}
    </>
  );
}

export default AlertOverlay;
