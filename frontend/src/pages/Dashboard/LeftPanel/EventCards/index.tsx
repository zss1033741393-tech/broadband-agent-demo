import { useNavigate } from 'react-router-dom';
import styles from './EventCards.module.css';

export interface EventItem {
  id: string;
  text: string;
  prefillMessage: string;
}

const MOCK_EVENTS: EventItem[] = [
  {
    id: 'evt_001',
    text: '用户9801357468@139.gd直播卡顿，需Wi-Fi远程调优，待确认执行',
    prefillMessage: '用户9801357468@139.gd反馈直播卡顿，请分析原因并提供Wi-Fi远程调优方案',
  },
  {
    id: 'evt_002',
    text: '用户9801357469@139.gd直播卡顿，需Wi-Fi远程调优，待确认执行',
    prefillMessage: '用户9801357469@139.gd反馈直播卡顿，请分析原因并提供Wi-Fi远程调优方案',
  },
];

function EventCards() {
  const navigate = useNavigate();

  const handleCardClick = (evt: EventItem) => {
    navigate('/workspace', {
      state: {
        eventId: evt.id,
        prefillMessage: evt.prefillMessage,
      },
    });
  };

  const handleAgree = (e: React.MouseEvent, evt: EventItem) => {
    e.stopPropagation();
    navigate('/workspace', {
      state: {
        eventId: evt.id,
        prefillMessage: evt.prefillMessage,
      },
    });
  };

  return (
    <div className={styles.section}>
      <div className={styles.sectionTitle}>
        人工带决策事件
        <span className={styles.badge}>{MOCK_EVENTS.length}</span>
      </div>
      <div className={styles.cardList}>
        {MOCK_EVENTS.map((evt) => (
          <div
            key={evt.id}
            className={styles.card}
            onClick={() => handleCardClick(evt)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === 'Enter' && handleCardClick(evt)}
          >
            <div className={styles.cardInner}>
              {/* 左侧红色圆形图标 */}
              <div className={styles.alertIcon}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                  <path d="M12 2L2 20h20L12 2z" fill="#ef4444" />
                  <path d="M12 9v5" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
                  <circle cx="12" cy="17" r="1" fill="#fff" />
                </svg>
              </div>
              {/* 文字区 */}
              <div className={styles.textArea}>
                <p className={styles.cardText}>{evt.text}</p>
                <button
                  type="button"
                  className={styles.agreeBtn}
                  onClick={(e) => handleAgree(e, evt)}
                >
                  同意
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default EventCards;
