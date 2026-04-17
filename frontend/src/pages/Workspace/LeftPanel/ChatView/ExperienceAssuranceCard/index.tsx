import type { ExperienceAssuranceRenderData } from '@/types/render';
import styles from './ExperienceAssuranceCard.module.css';

interface Props {
  data: ExperienceAssuranceRenderData;
}

const TASK_FIELD_LABELS: Record<string, string> = {
  neId: '设备 ID',
  neName: '设备名称',
  neIp: '设备 IP',
  fsp: 'FSP',
  onuId: 'ONU ID',
  servicePortIndex: '服务端口索引',
  serviceName: '服务名称',
  configStatus: '配置状态',
  runningStatus: '运行状态',
  configType: '配置类型',
  limitProfile: '限速模板',
  policyProfile: '策略模板',
  serviceType: '服务类型',
  taskId: '任务 ID',
  appCategory: '应用类别',
  appId: '应用 ID',
  appName: '应用名称',
  startTime: '开始时间',
  timeLimit: '时限（秒）',
};

const STATUS_LABELS: Record<string, Record<number, string>> = {
  configStatus: { 0: '未配置', 1: '已配置' },
  runningStatus: { 0: '未运行', 1: '运行中' },
};

function formatValue(key: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (key === 'timeLimit' && value === -1) return '无限制';
  if (key === 'configType' && value === -1) return '默认';
  if (key in STATUS_LABELS) {
    const label = STATUS_LABELS[key][value as number];
    if (label) return label;
  }
  return String(value);
}

function ExperienceAssuranceCard({ data }: Props) {
  const { businessType, isMock, taskData } = data;

  const rows = Object.entries(taskData)
    .filter(([key]) => key !== 'serviceType') // serviceType 已在 header 显示
    .map(([key, value]) => ({
      label: TASK_FIELD_LABELS[key] ?? key,
      value: formatValue(key, value),
      key,
    }));

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <span className={styles.icon}>⚙</span>
        <span className={styles.title}>差异化承载配置已下发</span>
        {isMock && <span className={styles.mockBadge}>模拟数据</span>}
        {businessType && <span className={styles.typeBadge}>{businessType}</span>}
      </div>
      <table className={styles.table}>
        <tbody>
          {rows.map(({ label, value, key }) => (
            <tr key={key} className={styles.row}>
              <td className={styles.labelCell}>{label}</td>
              <td className={styles.valueCell}>
                {key === 'runningStatus' ? (
                  <span className={value === '运行中' ? styles.statusOn : styles.statusOff}>
                    {value}
                  </span>
                ) : (
                  value
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default ExperienceAssuranceCard;
