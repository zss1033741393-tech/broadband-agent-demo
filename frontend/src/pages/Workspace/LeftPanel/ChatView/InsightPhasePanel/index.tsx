import { Tooltip } from 'antd';
import { CheckCircleFilled, SyncOutlined } from '@ant-design/icons';

import type { InsightState, InsightPhase, InsightStep, PhaseStatus } from '@/types/insight';
import styles from './InsightPhasePanel.module.css';

interface Props {
  state: InsightState;
}

function PhaseIcon({ status }: { status: PhaseStatus }) {
  if (status === 'done') return <CheckCircleFilled className={styles.iconDone} />;
  if (status === 'running') return <span className={styles.spinRing} />;
  if (status === 'reflected') return <SyncOutlined className={styles.iconReflected} />;
  return <span className={styles.iconPending}>○</span>;
}

function StepRow({ step }: { step: InsightStep }) {
  const label = step.rationale || step.insightTypes.join(' · ') || `Step ${step.stepId}`;
  return (
    <div className={`${styles.stepBlock} ${styles[`step_${step.status}`]}`}>
      <div className={styles.stepRow}>
        {step.status === 'done'
          ? <CheckCircleFilled className={styles.stepIconDone} />
          : step.status === 'running'
            ? <span className={styles.spinRingSmall} />
            : <span className={styles.stepDot} />
        }
        <span className={styles.stepLabel}>{label}</span>
        {step.significance !== undefined && step.status === 'done' && (
          <span className={styles.stepSig}>显著性 {step.significance.toFixed(2)}</span>
        )}
      </div>
      {step.summary && step.status === 'done' && (
        <div className={styles.stepSummary}>{step.summary}</div>
      )}
    </div>
  );
}

function PhaseRow({ phase }: { phase: InsightPhase }) {
  return (
    <div className={styles.phaseBlock}>
      <div className={styles.phaseHeader}>
        <PhaseIcon status={phase.status} />
        <span className={`${styles.phaseName} ${phase.status === 'running' ? styles.phaseNameActive : ''}`}>
          {phase.name}
        </span>
        {phase.reflection && (
          <Tooltip title={phase.reflection.reason} placement="right" overlayStyle={{ maxWidth: 280 }}>
            <span className={styles.reflectBadge}>已调整 ({phase.reflection.choice})</span>
          </Tooltip>
        )}
      </div>
      {phase.steps.length > 0 && (
        <div className={styles.stepList}>
          {phase.steps.map((s) => (
            <StepRow key={s.stepId} step={s} />
          ))}
        </div>
      )}
    </div>
  );
}

function InsightPhasePanel({ state }: Props) {
  const done = state.phases.filter((p) => p.status === 'done' || p.status === 'reflected').length;
  const total = state.totalPhases || state.phases.length;

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <span className={styles.panelTitle}>📊 洞察分析进度</span>
        <span className={styles.panelProgress}>{done} / {total}</span>
      </div>
      {state.goal && <div className={styles.goal}>{state.goal}</div>}
      <div className={styles.phaseList}>
        {state.phases.map((p) => (
          <PhaseRow key={p.phaseId} phase={p} />
        ))}
      </div>
    </div>
  );
}

export default InsightPhasePanel;
