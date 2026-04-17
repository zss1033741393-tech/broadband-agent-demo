import type { PlanGroup } from '@/api/protectionPlan';
import styles from './ProtectionPlanCard.module.css';

interface Props {
  groups: PlanGroup[];
}

function BoolBadge({ value }: { value: boolean }) {
  return (
    <span className={value ? styles.statusOn : styles.statusOff}>
      {value ? '已启用' : '未启用'}
    </span>
  );
}

function ProtectionPlanCard({ groups }: Props) {
  if (!groups.length) return null;

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <span className={styles.headerIcon}>🛡</span>
        <span className={styles.headerTitle}>当天该用户的保障方案</span>
      </div>
      <div className={styles.grid}>
        {groups.map((group) => (
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
        <p className={styles.footerLine}>请选择：</p>
        <p className={styles.footerLine}>1. 需要更新保障目标</p>
        <p className={styles.footerLine}>2. 直接编辑方案</p>
      </div>
    </div>
  );
}

export default ProtectionPlanCard;
