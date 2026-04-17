import styles from './ChatSection.module.css';

const ANALYSIS_TEXT =
  '当前网络存在多设备 CEI 低分问题，共识别出 10 个低分 PON 口和 10 个低分网关，最低 CEI 分数均为 54.08 分。根因定位显示，Rate 维度（速率维度）得分低是主要短板，其核心驱动指标为下行流量异常次数（rxTrafficHighCnt）过高，异常次数范围在 524-1208 次之间。时序分析进一步发现，问题集中爆发于18:00-21:00 晚高峰时段，该时段内流量波动显著，检测到 8 个明显变点。整体因果链路为：晚高峰下行流量异常频发 → 速率维度得分下滑 → CEI 总分降低。建议针对该时段及低分设备制定差异化承载保障或体验优化方案。';

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
