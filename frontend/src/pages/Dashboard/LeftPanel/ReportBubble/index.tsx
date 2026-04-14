import type { ChartItem } from '@/types/render';
import styles from './ReportBubble.module.css';

interface Props {
  content: string;
  charts: ChartItem[];
  onView: (content: string, charts: ChartItem[]) => void;
}

function ReportBubble({ content, charts, onView }: Props) {
  return (
    <div className={styles.bubble} onClick={() => onView(content, charts)}>
      <span className={styles.icon}>📄</span>
      <span className={styles.text}>点击查看报告</span>
      <span className={styles.arrow}>›</span>
    </div>
  );
}

export default ReportBubble;
