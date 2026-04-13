import { Tooltip } from 'antd';
import { BarChartOutlined, SettingOutlined, DashboardOutlined } from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';
import styles from './Sidebar.module.css';

function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();

  const isDashboard = location.pathname === '/' || location.pathname === '/dashboard';
  const isWorkspace = location.pathname === '/workspace';

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
        <Tooltip title="Agent 工作台" placement="right">
          <button
            type="button"
            className={`${styles.iconBtn} ${isWorkspace ? styles.active : ''}`}
            onClick={() => navigate('/workspace')}
            aria-label="Agent 工作台"
          >
            <BarChartOutlined />
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
