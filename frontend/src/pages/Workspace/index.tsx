import { useRef, useCallback } from 'react';
import { useLocation } from 'react-router-dom';
import TopBar from '@/components/Layout/TopBar';
import Sidebar from '@/components/Layout/Sidebar';
import LeftPanel from './LeftPanel';
import RightPanel from './RightPanel';
import styles from './Workspace.module.css';

const MIN_LEFT = 320;
const MAX_LEFT = 720;
const DEFAULT_LEFT = 484;

function Workspace() {
  const location = useLocation();
  const prefill = (location.state as { prefillMessage?: string } | null)?.prefillMessage;

  const leftWidth = useRef(DEFAULT_LEFT);
  const containerRef = useRef<HTMLDivElement>(null);
  const leftRef = useRef<HTMLDivElement>(null);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = leftWidth.current;

    const onMouseMove = (ev: MouseEvent) => {
      const next = Math.min(MAX_LEFT, Math.max(MIN_LEFT, startWidth + ev.clientX - startX));
      leftWidth.current = next;
      if (leftRef.current) leftRef.current.style.width = `${next}px`;
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    };

    const onMouseUp = () => {
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    };

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  }, []);

  return (
    <div className={styles.page}>
      <TopBar />
      <div className={styles.body}>
        <Sidebar />
        <div className={styles.workspace} ref={containerRef}>
          <div ref={leftRef} className={styles.leftWrap} style={{ width: DEFAULT_LEFT }}>
            <LeftPanel prefillMessage={prefill} />
          </div>
          <div className={styles.divider} onMouseDown={onMouseDown} />
          <RightPanel />
        </div>
      </div>
    </div>
  );
}

export default Workspace;
