import type { InsightEvent, InsightStep } from '@/types/insight';

type ParserState = 'NORMAL' | 'IN_MARKER' | 'IN_JSON' | 'CONSUME_NEWLINE';

export interface ParseResult {
  cleanText: string;
  events: InsightEvent[];
}

/**
 * 流式解析器：处理含有 <!--event:TYPE-->\n{JSON}\n 的 text 增量流。
 * 维护内部状态，每次调用 feed(delta) 返回干净文本和已提取的事件。
 */
export class InsightEventParser {
  private state: ParserState = 'NORMAL';
  private markerBuf = '';   // 正在积累的 <!--event:... 片段
  private eventType = '';   // 已解析出的事件类型
  private jsonBuf = '';     // 正在积累的 JSON 片段
  private depth = 0;        // JSON 括号深度

  feed(delta: string): ParseResult {
    const events: InsightEvent[] = [];
    let cleanText = '';

    for (let i = 0; i < delta.length; i++) {
      const ch = delta[i];

      if (this.state === 'NORMAL') {
        if (ch === '<') {
          this.markerBuf = '<';
          this.state = 'IN_MARKER';
        } else {
          cleanText += ch;
        }

      } else if (this.state === 'IN_MARKER') {
        this.markerBuf += ch;

        // 确认不是 <!--event: 前缀则退回 NORMAL
        const prefix = '<!--event:';
        if (!prefix.startsWith(this.markerBuf) && !this.markerBuf.startsWith(prefix)) {
          cleanText += this.markerBuf;
          this.markerBuf = '';
          this.state = 'NORMAL';
          continue;
        }

        // 完整匹配 <!--event:TYPE-->
        const endIdx = this.markerBuf.indexOf('-->');
        if (endIdx !== -1) {
          const inner = this.markerBuf.slice('<!--event:'.length, endIdx);
          this.eventType = inner.trim();
          this.markerBuf = '';
          this.jsonBuf = '';
          this.depth = 0;
          this.state = 'IN_JSON';
        }

      } else if (this.state === 'IN_JSON') {
        // 跳过 marker 后以及 JSON 前的空白换行
        if (this.jsonBuf === '' && (ch === '\n' || ch === '\r' || ch === ' ')) continue;

        this.jsonBuf += ch;

        if (ch === '{') this.depth++;
        if (ch === '}') {
          this.depth--;
          if (this.depth === 0 && this.jsonBuf.trim().length > 0) {
            // JSON 对象完整，消耗紧跟的换行（避免遗留到 cleanText）
            const evt = this._parseEvent(this.eventType, this.jsonBuf.trim());
            if (evt) events.push(evt);
            this.jsonBuf = '';
            this.eventType = '';
            this.state = 'CONSUME_NEWLINE';
          }
        }
      } else if ((this.state as string) === 'CONSUME_NEWLINE') {
        // 吃掉 JSON 结束后紧跟的换行符，然后回 NORMAL
        if (ch === '\n' || ch === '\r') continue;
        this.state = 'NORMAL';
        // 当前字符不是换行，重新处理
        i--;
      }
    }

    // 合并多余空行（3个以上\n压缩为2个）
    const collapsed = cleanText.replace(/\n{3,}/g, '\n\n');
    return { cleanText: collapsed, events };
  }

  reset() {
    this.state = 'NORMAL';
    this.markerBuf = '';
    this.eventType = '';
    this.jsonBuf = '';
    this.depth = 0;
  }

  private _parseEvent(type: string, json: string): InsightEvent | null {
    try {
      const d = JSON.parse(json);
      switch (type) {
        case 'plan':
          return {
            type: 'plan',
            goal: d.goal ?? '',
            totalPhases: d.total_phases ?? d.phases?.length ?? 0,
            phases: (d.phases ?? []).map((p: Record<string, unknown>) => ({
              phaseId: p.phase_id as number,
              name: p.name as string,
              milestone: (p.milestone as string) ?? '',
              description: (p.description as string) ?? '',
            })),
          };
        case 'decompose_result':
          return {
            type: 'decompose_result',
            phaseId: d.phase_id,
            steps: (d.steps ?? []).map((s: Record<string, unknown>) => ({
              stepId: s.step as number,
              insightTypes: (s.insight_types as string[]) ?? [],
              rationale: (s.rationale as string) ?? '',
              status: 'pending' as const,
            })),
          };
        case 'phase_start':
          return { type: 'phase_start', phaseId: d.phase_id };
        case 'step_result':
          return {
            type: 'step_result',
            phaseId: d.phase_id,
            stepId: d.step_id,
            summary: d.summary ?? '',
            significance: d.significance ?? 0,
            status: d.status ?? 'ok',
          };
        case 'reflect':
          return {
            type: 'reflect',
            phaseId: d.phase_id,
            choice: d.choice ?? '',
            reason: d.reason ?? '',
          };
        default:
          return null;
      }
    } catch {
      return null;
    }
  }
}

/** 将 InsightEvent 应用到 InsightState，返回新 state（immutable） */
export function applyInsightEvent(
  prev: import('@/types/insight').InsightState | undefined,
  event: InsightEvent,
): import('@/types/insight').InsightState {
  const empty: import('@/types/insight').InsightState = { goal: '', totalPhases: 0, phases: [] };
  const state = prev ?? empty;

  switch (event.type) {
    case 'plan':
      return {
        goal: event.goal,
        totalPhases: event.totalPhases,
        phases: event.phases.map((p) => ({
          ...p,
          status: 'pending',
          steps: [],
        })),
      };

    case 'decompose_result': {
      return {
        ...state,
        phases: state.phases.map((p) =>
          p.phaseId !== event.phaseId
            ? p
            : { ...p, steps: event.steps },
        ),
      };
    }

    case 'phase_start': {
      return {
        ...state,
        phases: state.phases.map((p) =>
          p.phaseId !== event.phaseId
            ? p
            : { ...p, status: 'running' },
        ),
      };
    }

    case 'step_result': {
      return {
        ...state,
        phases: state.phases.map((p) => {
          if (p.phaseId !== event.phaseId) return p;
          const steps: InsightStep[] = p.steps.map((s) =>
            s.stepId !== event.stepId
              ? s
              : { ...s, status: 'done', summary: event.summary, significance: event.significance },
          );
          // 所有 step 完成则 phase 也标为 done
          const allDone = steps.length > 0 && steps.every((s) => s.status === 'done');
          return { ...p, steps, status: allDone ? 'done' : p.status };
        }),
      };
    }

    case 'reflect': {
      return {
        ...state,
        phases: state.phases.map((p) =>
          p.phaseId !== event.phaseId
            ? p
            : {
                ...p,
                status: 'reflected',
                reflection: { choice: event.choice, reason: event.reason },
              },
        ),
      };
    }
  }
}
