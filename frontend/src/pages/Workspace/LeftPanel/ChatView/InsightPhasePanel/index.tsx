import { useState, useEffect, useRef, useCallback } from 'react';
import { Tooltip } from 'antd';
import { CheckCircleFilled, SyncOutlined, RightOutlined } from '@ant-design/icons';

import type { InsightState, InsightPhase, InsightStep, PhaseStatus } from '@/types/insight';
import type { Step } from '@/types/message';
import type { ChartItem } from '@/types/render';
import styles from './InsightPhasePanel.module.css';

interface Props {
  /** Insight 模式：传 InsightState */
  state?: InsightState;
  /** Planning 模式：传 steps 列表 */
  steps?: Step[];
  /** planning 模式下是否正在流式（用于判断哪个 step 是 running） */
  isStreaming?: boolean;

  /** 面板模式（浮动、可折叠、可拖拽） */
  collapsed?: boolean;
  onToggle?: () => void;

  /** 报告就绪时在底部左侧渲染查看按钮 */
  reportContent?: string;
  reportCharts?: ChartItem[];
  onViewReport?: (content: string, charts: ChartItem[]) => void;
}

// ── Insight 模式子组件 ──────────────────────────────────────────

function PhaseIcon({ status }: { status: PhaseStatus }) {
  if (status === 'done') return <CheckCircleFilled className={styles.iconDone} />;
  if (status === 'running') return <span className={styles.spinRing} />;
  if (status === 'reflected') return <SyncOutlined className={styles.iconReflected} />;
  return <span className={styles.iconPending}>○</span>;
}

function InsightStepRow({ step }: { step: InsightStep }) {
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

function InsightPhaseRow({ phase }: { phase: InsightPhase }) {
  const isDiscarded = phase.reflection?.choice === 'D';
  const isDone = phase.status === 'done' || phase.status === 'reflected';
  const hasSteps = phase.steps.length > 0;
  const [expanded, setExpanded] = useState(!isDone);

  useEffect(() => {
    if (isDone) setExpanded(false);
  }, [isDone]);

  const toggleable = hasSteps && isDone;

  return (
    <div className={`${styles.phaseBlock} ${isDiscarded ? styles.phaseDiscarded : ''}`}>
      <div
        className={`${styles.phaseHeader} ${toggleable ? styles.phaseHeaderClickable : ''}`}
        onClick={toggleable ? () => setExpanded((v) => !v) : undefined}
      >
        <PhaseIcon status={phase.status} />
        <span className={`
          ${styles.phaseName}
          ${phase.status === 'running' ? styles.phaseNameActive : ''}
          ${isDiscarded ? styles.phaseNameDiscarded : ''}
        `.trim()}>
          {phase.name}
        </span>
        {phase.reflection && (
          <Tooltip title={phase.reflection.reason} placement="right" overlayStyle={{ maxWidth: 280 }}>
            <span className={`${styles.reflectBadge} ${isDiscarded ? styles.reflectBadgeDiscarded : ''}`}>
              {isDiscarded ? '已删除 (D)' : `已调整 (${phase.reflection.choice})`}
            </span>
          </Tooltip>
        )}
        {toggleable && (
          <RightOutlined className={`${styles.phaseArrow} ${expanded ? styles.phaseArrowOpen : ''}`} />
        )}
      </div>
      {hasSteps && expanded && (
        <div className={styles.stepList}>
          {phase.steps.map((s) => (
            <InsightStepRow key={s.stepId} step={s} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Planning 模式子组件 ─────────────────────────────────────────

function useLiveElapsed(active: boolean): number {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef(Date.now());

  useEffect(() => {
    if (!active) { setElapsed(0); return; }
    startRef.current = Date.now();
    const id = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startRef.current) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, [active]);

  return elapsed;
}

function PlanningPhaseRow({ step, isRunning }: { step: Step; isRunning: boolean }) {
  const status: PhaseStatus = step.completed ? 'done' : isRunning ? 'running' : 'pending';
  const elapsed = useLiveElapsed(isRunning);

  return (
    <div className={styles.phaseBlock}>
      <div className={styles.phaseHeader}>
        <PhaseIcon status={status} />
        <span className={`${styles.phaseName} ${isRunning ? styles.phaseNameActive : ''}`}>
          {step.title}
        </span>
        {isRunning && (
          <span className={styles.elapsedBadge}>
            <span className={styles.elapsedDot} />
            {elapsed}s
          </span>
        )}
      </div>
    </div>
  );
}

// ── 主组件 ─────────────────────────────────────────────────────

const DEFAULT_HEIGHT = 350;
const MIN_HEIGHT = 42;

function InsightPhasePanel({
  state,
  steps,
  isStreaming,
  collapsed,
  onToggle,
  reportContent,
  reportCharts,
  onViewReport,
}: Props) {
  const isPanelMode = onToggle !== undefined;
  const [panelHeight, setPanelHeight] = useState(DEFAULT_HEIGHT);
  const [dragging, setDragging] = useState(false);
  const dragStartY = useRef(0);
  const dragStartH = useRef(0);

  // ── 拖拽调整高度 ────────────────────────────────────────────
  const onDragMouseDown = useCallback((e: React.MouseEvent) => {
    if (!isPanelMode) return;
    e.preventDefault();
    e.stopPropagation();
    setDragging(true);
    dragStartY.current = e.clientY;
    dragStartH.current = panelHeight;

    const onMouseMove = (ev: MouseEvent) => {
      const delta = ev.clientY - dragStartY.current; // 向下拖 → 变高
      const next = Math.min(600, Math.max(MIN_HEIGHT, dragStartH.current + delta));
      setPanelHeight(next);
    };
    const onMouseUp = () => {
      setDragging(false);
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    document.body.style.cursor = 'ns-resize';
    document.body.style.userSelect = 'none';
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  }, [isPanelMode, panelHeight]);

  // ── 统计进度 ────────────────────────────────────────────────
  let doneCount = 0;
  let totalCount = 0;

  if (state) {
    doneCount = state.phases.filter((p) => p.status === 'done' || p.status === 'reflected').length;
    totalCount = state.totalPhases || state.phases.length;
  } else if (steps) {
    doneCount = steps.filter((s) => s.completed).length;
    totalCount = steps.length;
  }

  // ── 正在 running 的 step（planning 模式）─────────────────────
  const runningStepId = (isStreaming && steps)
    ? [...steps].reverse().find((s) => !s.completed)?.stepId
    : undefined;

  // ── 样式 ────────────────────────────────────────────────────
  const panelClass = [
    styles.panel,
    isPanelMode ? styles.panelFixed : '',
    isPanelMode && collapsed ? styles.panelCollapsed : '',
    dragging ? styles.noTransition : '',
  ].filter(Boolean).join(' ');

  const panelStyle = isPanelMode && !collapsed
    ? { height: panelHeight }
    : undefined;

  return (
    <div className={panelClass} style={panelStyle}>
      {/* 头部 */}
      <div
        className={`${styles.panelHeader} ${isPanelMode ? styles.panelHeaderClickable : ''}`}
        onClick={isPanelMode ? onToggle : undefined}
      >
        <span className={styles.panelTitle}>进度跟踪</span>
        {state?.goal && !isPanelMode && (
          <span className={styles.goalInline}>{state.goal}</span>
        )}
        <span className={styles.panelProgress}>{doneCount} / {totalCount}</span>
        {isPanelMode && (
          <span className={`${styles.collapseChevron} ${collapsed ? styles.chevronCollapsed : styles.chevronExpanded}`} />
        )}
      </div>

      {/* 拖拽手柄（面板模式展开时显示，在 header 下方） */}
      {isPanelMode && !collapsed && (
        <div
          className={styles.dragHandle}
          onMouseDown={onDragMouseDown}
        />
      )}

      {/* 内容区 */}
      {(!isPanelMode || !collapsed) && (
        <>
          {state?.goal && isPanelMode && (
            <div className={styles.goal}>{state.goal}</div>
          )}

          <div className={styles.phaseList}>
            {/* Insight 模式 */}
            {state && state.phases.map((p) => (
              <InsightPhaseRow key={p.phaseId} phase={p} />
            ))}
            {/* Planning 模式 */}
            {steps && steps.map((s) => (
              <PlanningPhaseRow
                key={s.stepId}
                step={s}
                isRunning={s.stepId === runningStepId}
              />
            ))}
          </div>

          {/* 报告按钮 */}
          {onViewReport && reportContent !== undefined && reportCharts !== undefined && (
            <div className={styles.reportFooter}>
              <button
                className={styles.reportBtn}
                type="button"
                onClick={() => onViewReport(reportContent, reportCharts)}
              >
                <span className={styles.reportIcon}>📄</span>
                <span className={styles.reportText}>点击查看报告</span>
                <span className={styles.reportArrow}>→</span>
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default InsightPhasePanel;
