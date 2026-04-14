import type { ChartItem } from '@/types/render';
import styles from './ReportFloatBtn.module.css';

interface Props {
  content: string;
  charts: ChartItem[];
  onView: (content: string, charts: ChartItem[]) => void;
}

function ReportFloatBtn({ content, charts, onView }: Props) {
  return (
    <div className={styles.wrap}>
      <button
        className={styles.btn}
        onClick={() => onView(content, charts)}
        type="button"
      >
        <span className={styles.icon}>📄</span>
        <span className={styles.text}>点击查看报告</span>
        <span className={styles.arrow}>→</span>
      </button>
    </div>
  );
}

export default ReportFloatBtn;
