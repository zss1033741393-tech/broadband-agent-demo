import type { PlanGroup } from '@/api/protectionPlan';
import styles from './ProtectionPlanCard.module.css';

interface Props {
  groups: PlanGroup[];
}

function ProtectionPlanCard({ groups }: Props) {
  if (!groups.length) return null;

  return (
    <div className={styles.card}>
      <div className={styles.header}>当天该用户的保障方案</div>

      {groups.map((group) => (
        <div key={group.title} className={styles.group}>
          <div className={styles.groupTitle}>{group.title}</div>
          <div className={styles.items}>
            {group.items.map((item) => (
              <div key={item.label} className={styles.item}>
                <span className={styles.label}>{item.label}：</span>
                {typeof item.value === 'boolean' ? (
                  <span
                    className={`${styles.valueBool} ${item.value ? styles.valueOn : styles.valueOff}`}
                  >
                    {item.value ? '开启' : '关闭'}
                  </span>
                ) : (
                  <span className={styles.valueStr}>{item.value}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}

      <div className={styles.footer}>
        请选择：<br />
        1. 需要更新保障目标<br />
        2. 直接编辑方案
      </div>
    </div>
  );
}

export default ProtectionPlanCard;
