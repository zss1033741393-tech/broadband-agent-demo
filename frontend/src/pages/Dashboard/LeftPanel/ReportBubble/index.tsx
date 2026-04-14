import styles from './ReportBubble.module.css';

interface Props {
  content: string;
  onView: (content: string) => void;
}

function ReportBubble({ content, onView }: Props) {
  return (
    <div className={styles.bubble} onClick={() => onView(content)}>
      <span className={styles.icon}>📄</span>
      <span className={styles.text}>点击查看报告</span>
      <span className={styles.arrow}>›</span>
    </div>
  );
}

export default ReportBubble;
