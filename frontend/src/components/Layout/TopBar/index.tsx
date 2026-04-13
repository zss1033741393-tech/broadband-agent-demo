import { MoonOutlined, UserOutlined, ExclamationCircleOutlined, QuestionCircleOutlined } from '@ant-design/icons';
import styles from './TopBar.module.css';

function TopBar() {
  return (
    <header className={styles.topBar}>
      {/* 左侧 LOGO */}
      <div className={styles.logoArea}>
        <div className={styles.logoPlaceholder} title="光接入智能体">
          <span className={styles.logoText}>光智</span>
        </div>
      </div>

      {/* 中间标题 */}
      <div className={styles.titleArea}>
        <span className={styles.title}>光接入智能体</span>
      </div>

      {/* 右侧图标组 */}
      <div className={styles.rightArea}>
        <button type="button" className={styles.iconBtn} title="切换主题">
          <MoonOutlined />
        </button>
        <button type="button" className={styles.iconBtn} title="用户">
          <span className={styles.userGroup}>
            <UserOutlined className={styles.userIcon} />
            <span className={styles.userName}>admin</span>
          </span>
        </button>
        <button type="button" className={styles.iconBtn} title="通知">
          <ExclamationCircleOutlined />
        </button>
        <button type="button" className={styles.iconBtn} title="帮助">
          <QuestionCircleOutlined />
        </button>
      </div>
    </header>
  );
}

export default TopBar;
