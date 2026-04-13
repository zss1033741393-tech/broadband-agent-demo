import styles from './StatBar.module.css';

interface StatItem {
  label: string;
  value: string;
  color: 'white' | 'green';
  icon: React.ReactNode;
}

const STATS: StatItem[] = [
  {
    label: '事件总数',
    value: '14,330',
    color: 'white',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="10" stroke="#6b7280" strokeWidth="1.5" />
        <path d="M12 8v4l3 3" stroke="#6b7280" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    label: '正在处置中',
    value: '14,328',
    color: 'green',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
        <path d="M12 2L2 7l10 5 10-5-10-5z" stroke="#22c55e" strokeWidth="1.5" strokeLinejoin="round" />
        <path d="M2 17l10 5 10-5" stroke="#22c55e" strokeWidth="1.5" strokeLinejoin="round" />
        <path d="M2 12l10 5 10-5" stroke="#22c55e" strokeWidth="1.5" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    label: '已处置',
    value: '2',
    color: 'white',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
        <path d="M20 6L9 17l-5-5" stroke="#6b7280" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
];

function StatBar() {
  return (
    <div className={styles.statBar}>
      {STATS.map((stat) => (
        <div key={stat.label} className={styles.statItem}>
          <div className={styles.iconRow}>
            {stat.icon}
            <span className={styles.label}>{stat.label}</span>
          </div>
          <div className={`${styles.value} ${styles[stat.color]}`}>
            {stat.value}
            <span className={styles.unit}>个</span>
          </div>
        </div>
      ))}
    </div>
  );
}

export default StatBar;
