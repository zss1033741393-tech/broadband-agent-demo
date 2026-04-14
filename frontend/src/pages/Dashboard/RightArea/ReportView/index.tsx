import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import styles from './ReportView.module.css';

interface Props {
  content: string;
  onBack: () => void;
}

function ReportView({ content, onBack }: Props) {
  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <span className={styles.title}>网络性能分析报告</span>
        <button className={styles.backBtn} onClick={onBack}>
          ‹ 返回地图
        </button>
      </div>
      <div className={styles.scroll}>
        <div className={styles.content}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}

export default ReportView;
