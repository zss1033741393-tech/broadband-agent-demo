import styles from './ChatSection.module.css';

const ANALYSIS_TEXT =
  '当前区域出现 PON 口拥塞问题，XX-PON-03 至 XX-PON-07 共 5 个口在峰值时段（18:00–22:00）' +
  '下行带宽利用率持续超过 85%，已累计产生 23 户卡顿投诉。建议优先排查 XX-PON-05 高流量' +
  '挂载用户，并评估实施流量调优或用户迁移方案以缓解拥塞压力。';

interface Props {
  convId: string | null;
}

/** 展示固定网络级分析结论文字 */
function ChatSection({ convId: _convId }: Props) {
  return (
    <div className={styles.chatSection}>
      <div className={styles.sectionTitle}>网络级分析结论</div>
      <div className={styles.messageArea}>
        <div className={styles.analysisText}>{ANALYSIS_TEXT}</div>
      </div>
    </div>
  );
}

export default ChatSection;
