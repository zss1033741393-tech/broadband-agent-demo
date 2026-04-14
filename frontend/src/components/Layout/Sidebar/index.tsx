import { Tooltip } from 'antd';
import { SettingOutlined, DashboardOutlined, SearchOutlined, HistoryOutlined } from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';
import { useWorkspaceStore } from '@/store/workspaceStore';
import styles from './Sidebar.module.css';

function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const leftView = useWorkspaceStore((s) => s.leftView);
  const backToList = useWorkspaceStore((s) => s.backToList);

  const isDashboard = location.pathname === '/' || location.pathname === '/dashboard';
  const isWorkspace = location.pathname === '/workspace';
  const isUserQuery = isWorkspace && leftView === 'chat';
  const isHistory = isWorkspace && leftView === 'list';

  return (
    <nav className={styles.sidebar}>
      <div className={styles.iconGroup}>
        <Tooltip title="总览大屏" placement="right">
          <button
            type="button"
            className={`${styles.iconBtn} ${isDashboard ? styles.active : ''}`}
            onClick={() => navigate('/dashboard')}
            aria-label="总览大屏"
          >
            <DashboardOutlined />
          </button>
        </Tooltip>

        <Tooltip title="用户级问题查询入口" placement="right">
          <button
            type="button"
            className={`${styles.iconBtn} ${isUserQuery ? styles.active : ''}`}
            onClick={() => navigate('/workspace', { state: { newConversation: true } })}
            aria-label="用户级问题查询入口"
          >
            <SearchOutlined />
          </button>
        </Tooltip>

        <Tooltip title="历史会话" placement="right">
          <button
            type="button"
            className={`${styles.iconBtn} ${isHistory ? styles.active : ''}`}
            onClick={() => { navigate('/workspace'); backToList(); }}
            aria-label="历史会话"
          >
            <HistoryOutlined />
          </button>
        </Tooltip>
      </div>

      <div className={styles.bottomGroup}>
        <Tooltip title="设置" placement="right">
          <button type="button" className={styles.iconBtn} aria-label="设置">
            <SettingOutlined />
          </button>
        </Tooltip>
      </div>
    </nav>
  );
}

export default Sidebar;
