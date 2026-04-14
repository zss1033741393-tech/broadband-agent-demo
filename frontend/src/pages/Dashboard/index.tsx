import { useState } from 'react';
import TopBar from '@/components/Layout/TopBar';
import Sidebar from '@/components/Layout/Sidebar';
import DashboardLeftPanel from './LeftPanel';
import RightArea from './RightArea';
import styles from './Dashboard.module.css';
import type { ChartItem } from '@/types/render';

function Dashboard() {
  const [rightView, setRightView] = useState<'map' | 'report'>('map');
  const [reportContent, setReportContent] = useState('');
  const [reportCharts, setReportCharts] = useState<ChartItem[]>([]);

  const handleViewReport = (content: string, charts: ChartItem[]) => {
    setReportContent(content);
    setReportCharts(charts);
    setRightView('report');
  };

  return (
    <div className={styles.page}>
      <TopBar />
      <div className={styles.body}>
        <Sidebar />
        <DashboardLeftPanel onViewReport={handleViewReport} />
        <RightArea
          view={rightView}
          reportContent={reportContent}
          reportCharts={reportCharts}
          onBack={() => setRightView('map')}
        />
      </div>
    </div>
  );
}

export default Dashboard;
