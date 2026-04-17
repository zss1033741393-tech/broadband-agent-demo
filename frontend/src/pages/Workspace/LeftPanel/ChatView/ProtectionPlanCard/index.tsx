import styles from './ProtectionPlanCard.module.css';

interface KVItem {
  label: string;
  value: string | boolean;
}

interface Group {
  title: string;
  items: KVItem[];
}

const GROUPS: Group[] = [
  {
    title: 'AP补点推荐',
    items: [
      { label: 'WIFI信号仿真', value: false },
      { label: '应用卡顿仿真', value: false },
      { label: 'AP补点推荐', value: false },
    ],
  },
  {
    title: 'CEI体验感知',
    items: [
      { label: 'CEI模型', value: '普通' },
      { label: 'CEI粒度', value: '天级' },
      { label: 'CEI阈值', value: '70分' },
    ],
  },
  {
    title: '故障诊断',
    items: [
      { label: '诊断场景', value: '上网慢 | 无法上网 | 游戏卡顿 | 直播卡顿' },
      { label: '偶发卡顿定界', value: false },
    ],
  },
  {
    title: '远程优化',
    items: [
      { label: '触发时间', value: '定时' },
      { label: 'WIFI信道切换', value: true },
      { label: '网关重启', value: true },
      { label: 'WIFI功率调优', value: true },
    ],
  },
  {
    title: '差异化承载',
    items: [
      { label: '差异化承载', value: false },
    ],
  },
];

const FOOTER_TEXT = '请选择：\n1. 需要更新保障目标\n2. 直接编辑方案';

function BoolBadge({ value }: { value: boolean }) {
  return (
    <span className={value ? styles.statusOn : styles.statusOff}>
      {value ? '已启用' : '未启用'}
    </span>
  );
}

function ProtectionPlanCard() {
  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <span className={styles.headerIcon}>🛡</span>
        <span className={styles.headerTitle}>当天该用户的保障方案</span>
      </div>
      <div className={styles.grid}>
        {GROUPS.map((group) => (
          <div key={group.title} className={styles.group}>
            <div className={styles.groupTitle}>{group.title}</div>
            <div className={styles.rows}>
              {group.items.map((item) => (
                <div key={item.label} className={styles.row}>
                  <span className={styles.label}>{item.label}</span>
                  {typeof item.value === 'boolean' ? (
                    <BoolBadge value={item.value} />
                  ) : (
                    <span className={styles.valueText}>{item.value}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className={styles.footer}>
        {FOOTER_TEXT.split('\n').map((line, i) => (
          <p key={i} className={styles.footerLine}>{line}</p>
        ))}
      </div>
    </div>
  );
}

export default ProtectionPlanCard;
