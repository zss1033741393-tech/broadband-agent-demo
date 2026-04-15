/** 右侧渲染块类型定义 */

export interface ImageRenderData {
  imageId: string;
  imageUrl: string;
  title: string;
  kind?: string;
  conclusion?: string;
}

export interface ChartItem {
  chartId: string;
  title: string;
  conclusion: string;
  // ECharts option，结构由后端决定，前端直接透传
  echartsOption: Record<string, unknown>;
  phaseId?: number;
  stepId?: number;
}

export interface InsightRenderData {
  charts: ChartItem[];
  markdownReport: string;
}

export type RenderBlock =
  | { renderType: 'image'; renderData: ImageRenderData }
  | { renderType: 'insight'; renderData: InsightRenderData };
