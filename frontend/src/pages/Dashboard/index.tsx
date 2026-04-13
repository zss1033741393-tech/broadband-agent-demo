import TopBar from '@/components/Layout/TopBar';
import Sidebar from '@/components/Layout/Sidebar';
import DashboardLeftPanel from './LeftPanel';
import RightArea from './RightArea';
import styles from './Dashboard.module.css';

function Dashboard() {
  return (
    <div className={styles.page}>
      <TopBar />
      <div className={styles.body}>
        <Sidebar />
        <DashboardLeftPanel />
        <RightArea />
      </div>
    </div>
  );
}

export default Dashboard;
