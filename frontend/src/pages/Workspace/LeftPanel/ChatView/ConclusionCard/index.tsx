import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import styles from './ConclusionCard.module.css';

interface Props {
  content: string;
  streaming?: boolean;
}

function ConclusionCard({ content, streaming }: Props) {
  if (!content || !content.trim()) return null;

  return (
    <div className={styles.card}>
      <div className={styles.contentBlock}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        {streaming && <span className={styles.cursor} />}
      </div>
    </div>
  );
}

export default ConclusionCard;
