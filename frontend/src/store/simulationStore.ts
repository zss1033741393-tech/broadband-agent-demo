import { create } from 'zustand';
import { parseSseStream } from '@/utils/sseParser';
import * as simApi from '@/api/simulation';

// ─────────────────────────────────────────────────────────────────────────────
// Public types
// ─────────────────────────────────────────────────────────────────────────────

export interface SimSummary {
  stallRate: number;
  avgThroughput: number;
  tcpBlockRatio: number;
  bandwidthMeetRate: number;
}

export interface SimSegment {
  startIdx: number;
  endIdx: number;
  type: 'baseline' | 'fault' | 'recovery';
}

export type SimBubbleEvent =
  | { id: string; kind: 'user'; text: string }
  | { id: string; kind: 'system'; text: string }
  | {
      id: string;
      kind: 'comparison';
      faultName: string;
      measures: string[];
      faultSummary: SimSummary;
      recoverySummary: SimSummary;
    };

export interface ChartData {
  step: number[];
  throughput: number[];
  buffer: number[];
  stall: number[];
  tcpRetrans: number[];
  jitter: number[];
  frameGen: number[];
  frameDrop: number[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Internal types
// ─────────────────────────────────────────────────────────────────────────────

interface SimBatchPayload {
  batchIndex: number;
  segType: string;
  data: {
    step: number[];
    effective_up_throughput: number[];
    buffer_watermark: number[];
    stall_active: number[];
    tcp_retrans_rate: number[];
    up_jitter: number[];
    frame_gen_flag: number[];
    frame_drop_flag: number[];
  };
}

interface SimSegEndPayload {
  segType: string;
  summary: SimSummary;
  faultName?: string;
  measures?: string[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Store interface
// ─────────────────────────────────────────────────────────────────────────────

interface SimulationState {
  active: boolean;
  streaming: boolean;
  phase: 'idle' | 'baseline' | 'fault' | 'recovery';
  chartData: ChartData;
  segments: SimSegment[];
  summaries: SimSummary[];
  convId: string | null;
  currentFaultName: string;
  simEvents: SimBubbleEvent[];

  // ── internal ──
  _abortCtrl: AbortController | null;
  _lastSegType: string;
  _eventSeq: number;

  pendingFaultName: string;
  resetKey: number;

  // ── actions ──
  addUserEvent: (text: string) => void;
  addSystemEvent: (text: string) => void;
  startSimulation: (convId: string, faultName?: string) => Promise<void>;
  injectFault: (convId: string, faultName: string) => Promise<void>;
  remediate: () => Promise<void>;
  reset: () => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

const emptyChartData = (): ChartData => ({
  step: [],
  throughput: [],
  buffer: [],
  stall: [],
  tcpRetrans: [],
  jitter: [],
  frameGen: [],
  frameDrop: [],
});

// ─────────────────────────────────────────────────────────────────────────────
// Store
// ─────────────────────────────────────────────────────────────────────────────

export const useSimulationStore = create<SimulationState>((set, get) => ({
  active: false,
  streaming: false,
  phase: 'idle',
  chartData: emptyChartData(),
  segments: [],
  summaries: [],
  convId: null,
  currentFaultName: '',
  pendingFaultName: '',
  resetKey: 0,
  simEvents: [],
  _abortCtrl: null,
  _lastSegType: '',
  _eventSeq: 0,

  addUserEvent: (text: string) => {
    set((s) => ({
      simEvents: [...s.simEvents, { id: `sim-${s._eventSeq + 1}`, kind: 'user' as const, text }],
      _eventSeq: s._eventSeq + 1,
    }));
  },

  addSystemEvent: (text: string) => {
    set((s) => ({
      simEvents: [...s.simEvents, { id: `sim-${s._eventSeq + 1}`, kind: 'system' as const, text }],
      _eventSeq: s._eventSeq + 1,
    }));
  },

  startSimulation: async (convId: string, faultName?: string) => {
    get()._abortCtrl?.abort();
    const ctrl = new AbortController();
    const startText = faultName
      ? `仿真已启动，正在运行基线段（后台计算中，请稍候）...（基线完成后将自动注入故障：${faultName}）`
      : '仿真已启动，正在运行基线段（后台计算中，请稍候）...';
    set((s) => ({
      active: true,
      streaming: true,
      phase: 'baseline',
      convId,
      chartData: emptyChartData(),
      segments: [],
      summaries: [],
      currentFaultName: '',
      pendingFaultName: faultName ?? '',
      resetKey: s.resetKey + 1,
      _abortCtrl: ctrl,
      _lastSegType: '',
      simEvents: [
        ...s.simEvents,
        { id: `sim-${s._eventSeq + 1}`, kind: 'system' as const, text: startText },
      ],
      _eventSeq: s._eventSeq + 1,
    }));

    let resp: Response;
    try {
      resp = await simApi.startSimulation(convId, ctrl.signal);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      set((s) => ({
        streaming: false,
        active: false,
        simEvents: [
          ...s.simEvents,
          { id: `sim-${s._eventSeq + 1}`, kind: 'system' as const, text: `❌ 仿真启动失败：${msg}（请确认后端已启动）` },
        ],
        _eventSeq: s._eventSeq + 1,
      }));
      return;
    }

    try {
      await parseSseStream(
        resp,
        (e) => {
          if (e.event === 'sim_batch') _handleBatch(e.data as SimBatchPayload);
          else if (e.event === 'sim_segment_end') _handleSegEnd(e.data as SimSegEndPayload);
          else if (e.event === 'sim_error') {
            const errMsg = (e.data as { message?: string })?.message ?? '未知错误';
            set((s) => ({
              streaming: false,
              simEvents: [
                ...s.simEvents,
                { id: `sim-${s._eventSeq + 1}`, kind: 'system' as const, text: `❌ 仿真引擎错误：${errMsg}` },
              ],
              _eventSeq: s._eventSeq + 1,
            }));
          }
        },
        ctrl.signal,
      );
    } catch (err) {
      if (ctrl.signal.aborted) return;
      const msg = err instanceof Error ? err.message : String(err);
      set((s) => ({
        streaming: false,
        simEvents: [
          ...s.simEvents,
          { id: `sim-${s._eventSeq + 1}`, kind: 'system' as const, text: `❌ 数据流中断：${msg}` },
        ],
        _eventSeq: s._eventSeq + 1,
      }));
    }
  },

  injectFault: async (convId: string, faultName: string) => {
    get()._abortCtrl?.abort();
    const ctrl = new AbortController();
    set((s) => ({
      streaming: true,
      phase: 'fault' as const,
      currentFaultName: faultName,
      _abortCtrl: ctrl,
      simEvents: [
        ...s.simEvents,
        {
          id: `sim-${s._eventSeq + 1}`,
          kind: 'system' as const,
          text: `正在注入故障：${faultName}...`,
        },
      ],
      _eventSeq: s._eventSeq + 1,
    }));

    let resp: Response;
    try {
      resp = await simApi.injectFault(convId, faultName, ctrl.signal);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      set((s) => ({
        streaming: false,
        simEvents: [
          ...s.simEvents,
          { id: `sim-${s._eventSeq + 1}`, kind: 'system' as const, text: `❌ 故障注入失败：${msg}` },
        ],
        _eventSeq: s._eventSeq + 1,
      }));
      return;
    }

    try {
      await parseSseStream(
        resp,
        (e) => {
          if (e.event === 'sim_batch') _handleBatch(e.data as SimBatchPayload);
          else if (e.event === 'sim_segment_end') _handleSegEnd(e.data as SimSegEndPayload);
          else if (e.event === 'sim_error') {
            const errMsg = (e.data as { message?: string })?.message ?? '未知错误';
            set((s) => ({
              streaming: false,
              simEvents: [
                ...s.simEvents,
                { id: `sim-${s._eventSeq + 1}`, kind: 'system' as const, text: `❌ 故障段错误：${errMsg}` },
              ],
              _eventSeq: s._eventSeq + 1,
            }));
          }
        },
        ctrl.signal,
      );
    } catch (err) {
      if (ctrl.signal.aborted) return;
      const msg = err instanceof Error ? err.message : String(err);
      set((s) => ({
        streaming: false,
        simEvents: [
          ...s.simEvents,
          { id: `sim-${s._eventSeq + 1}`, kind: 'system' as const, text: `❌ 数据流中断：${msg}` },
        ],
        _eventSeq: s._eventSeq + 1,
      }));
    }
  },

  remediate: async () => {
    const { convId } = get();
    if (!convId) return;
    get()._abortCtrl?.abort();
    const ctrl = new AbortController();
    set({ streaming: true, phase: 'recovery', _abortCtrl: ctrl });

    let resp: Response;
    try {
      resp = await simApi.remediate(convId, ctrl.signal);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      set((s) => ({
        streaming: false,
        simEvents: [
          ...s.simEvents,
          { id: `sim-${s._eventSeq + 1}`, kind: 'system' as const, text: `❌ 自愈启动失败：${msg}` },
        ],
        _eventSeq: s._eventSeq + 1,
      }));
      return;
    }

    try {
      await parseSseStream(
        resp,
        (e) => {
          if (e.event === 'sim_batch') _handleBatch(e.data as SimBatchPayload);
          else if (e.event === 'sim_segment_end') _handleSegEnd(e.data as SimSegEndPayload);
          else if (e.event === 'sim_error') {
            const errMsg = (e.data as { message?: string })?.message ?? '未知错误';
            set((s) => ({
              streaming: false,
              simEvents: [
                ...s.simEvents,
                { id: `sim-${s._eventSeq + 1}`, kind: 'system' as const, text: `❌ 自愈段错误：${errMsg}` },
              ],
              _eventSeq: s._eventSeq + 1,
            }));
          }
        },
        ctrl.signal,
      );
    } catch (err) {
      if (ctrl.signal.aborted) return;
      const msg = err instanceof Error ? err.message : String(err);
      set((s) => ({
        streaming: false,
        simEvents: [
          ...s.simEvents,
          { id: `sim-${s._eventSeq + 1}`, kind: 'system' as const, text: `❌ 数据流中断：${msg}` },
        ],
        _eventSeq: s._eventSeq + 1,
      }));
    }
  },

  reset: () => {
    get()._abortCtrl?.abort();
    set((s) => ({
      active: false,
      streaming: false,
      phase: 'idle',
      chartData: emptyChartData(),
      segments: [],
      summaries: [],
      convId: null,
      currentFaultName: '',
      pendingFaultName: '',
      resetKey: s.resetKey + 1,
      simEvents: [],
      _abortCtrl: null,
      _lastSegType: '',
    }));
  },
}));

// ─────────────────────────────────────────────────────────────────────────────
// Internal event handlers (outside store for readability)
// ─────────────────────────────────────────────────────────────────────────────

function _handleBatch(payload: SimBatchPayload): void {
  if (payload.batchIndex === 0) {
    console.log('[sim] first batch received, segType=', payload.segType, 'steps=', payload.data.step?.length);
  }
  useSimulationStore.setState((s) => {
    const prevLen = s.chartData.step.length;
    const segType = payload.segType as SimSegment['type'];
    const d = payload.data;

    // Start a new segment entry when phase changes
    let segments = s.segments;
    if (segType !== s._lastSegType) {
      segments = [...segments, { startIdx: prevLen, endIdx: prevLen, type: segType }];
    }

    const newChartData: ChartData = {
      step: [...s.chartData.step, ...d.step],
      throughput: [...s.chartData.throughput, ...d.effective_up_throughput],
      buffer: [...s.chartData.buffer, ...d.buffer_watermark],
      stall: [...s.chartData.stall, ...d.stall_active],
      tcpRetrans: [...s.chartData.tcpRetrans, ...d.tcp_retrans_rate],
      jitter: [...s.chartData.jitter, ...d.up_jitter],
      frameGen: [...s.chartData.frameGen, ...d.frame_gen_flag],
      frameDrop: [...s.chartData.frameDrop, ...d.frame_drop_flag],
    };

    const updatedSegments = segments.map((seg, i) =>
      i === segments.length - 1
        ? { ...seg, endIdx: newChartData.step.length - 1 }
        : seg,
    );

    return { chartData: newChartData, segments: updatedSegments, _lastSegType: segType };
  });
}

function _handleSegEnd(payload: SimSegEndPayload): void {
  useSimulationStore.setState((s) => {
    const summaries = [...s.summaries, payload.summary];
    const seq = s._eventSeq;

    if (payload.segType === 'baseline') {
      const { pendingFaultName, convId } = s;
      if (pendingFaultName && convId) {
        // 保持 streaming: true，避免图表视窗跳回基线全览再重新滚动
        setTimeout(() => { void useSimulationStore.getState().injectFault(convId, pendingFaultName); }, 0);
        return { summaries, pendingFaultName: '', _eventSeq: seq };
      }
      return { summaries, streaming: false, _eventSeq: seq };
    }

    if (payload.segType === 'fault') {
      const diagText = `🔍 调用故障树，定界定位的结果为：${s.currentFaultName}。正在执行对应的远程闭环措施...`;
      const newEvt: SimBubbleEvent = {
        id: `sim-${seq + 1}`,
        kind: 'system',
        text: diagText,
      };
      // 保持 streaming: true，避免图表视窗跳回全览再重新滚动
      setTimeout(() => { void useSimulationStore.getState().remediate(); }, 0);
      return { summaries, streaming: true, simEvents: [...s.simEvents, newEvt], _eventSeq: seq + 1 };
    }

    if (payload.segType === 'recovery') {
      const faultSummary = summaries[summaries.length - 2];
      const recoverySummary = summaries[summaries.length - 1];
      const compEvt: SimBubbleEvent = {
        id: `sim-${seq + 1}`,
        kind: 'comparison',
        faultName: payload.faultName ?? s.currentFaultName,
        measures: payload.measures ?? [],
        faultSummary,
        recoverySummary,
      };
      return {
        summaries,
        streaming: false,
        simEvents: [...s.simEvents, compEvt],
        _eventSeq: seq + 1,
      };
    }

    return { summaries };
  });
}
