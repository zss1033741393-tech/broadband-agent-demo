import { http, HttpResponse } from 'msw';
import conversations from '@mock/conversations.json';
import createResp from '@mock/conversation-create.json';
import deleteResp from '@mock/conversation-delete.json';
import messagesConv001 from '@mock/messages-conv_001.json';
import messagesConv002 from '@mock/messages-conv_002.json';
import messagesConv003 from '@mock/messages-conv_003.json';
import messagesConv004 from '@mock/messages-conv_004.json';
import sseImage from '@mock/sse-stream-image.json';
import sseInsight from '@mock/sse-stream-insight.json';
import sseError from '@mock/sse-stream-error.json';
import sseReport from '@mock/sse-stream-report.json';
import { replaySse, type SseEvent } from './sseReplay';

const messagesMap: Record<string, unknown> = {
  conv_001: messagesConv001,
  conv_002: messagesConv002,
  conv_003: messagesConv003,
  conv_004: messagesConv004,
};

const emptyMessages = { code: 0, message: 'success', data: { list: [] } };

export const handlers = [
  // 获取会话列表
  http.get('/api/conversations', () => HttpResponse.json(conversations)),

  // 新建会话
  http.post('/api/conversations', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as { title?: string };
    const data = JSON.parse(JSON.stringify(createResp));
    if (body?.title) data.data.title = body.title;
    // 新会话给一个稍微随机的 id，避免重复
    data.data.id = `conv_new_${Date.now()}`;
    data.data.createdAt = new Date().toISOString();
    data.data.updatedAt = data.data.createdAt;
    return HttpResponse.json(data);
  }),

  // 删除会话
  http.delete('/api/conversations/:id', () => HttpResponse.json(deleteResp)),

  // 获取会话历史消息
  http.get('/api/conversations/:id/messages', ({ params }) => {
    const id = params.id as string;
    const data = messagesMap[id] ?? emptyMessages;
    return HttpResponse.json(data);
  }),

  // 发送消息（SSE 流式）
  http.post('/api/conversations/:id/messages', async ({ request, params }) => {
    const id = params.id as string;
    const body = (await request.json().catch(() => ({}))) as { content?: string };
    const content = body?.content ?? '';
    let stream: { events: SseEvent[] };
    if (/error|失败|超时|出错/.test(content)) {
      stream = sseError as { events: SseEvent[] };
    } else if (/报告|洞察|insight|周报|性能/.test(content)) {
      stream = sseInsight as { events: SseEvent[] };
    } else if (id.startsWith('conv_new_')) {
      // Dashboard 新建会话 → 返回报告流
      stream = sseReport as { events: SseEvent[] };
    } else {
      stream = sseImage as { events: SseEvent[] };
    }
    return replaySse(stream.events);
  }),

  // 获取保障方案
  http.get('/api/protection-plan', () =>
    HttpResponse.json({
      code: 0,
      message: 'success',
      data: {
        groups: [
          { title: 'AP补点推荐', items: [
            { label: 'WIFI信号仿真', value: false },
            { label: '应用卡顿仿真', value: false },
            { label: 'AP补点推荐', value: false },
          ]},
          { title: 'CEI体验感知', items: [
            { label: 'CEI模型', value: '普通' },
            { label: 'CEI粒度', value: '天级' },
            { label: 'CEI阈值', value: '70分' },
          ]},
          { title: '故障诊断', items: [
            { label: '诊断场景', value: '上网慢 | 无法上网 | 游戏卡顿 | 直播卡顿' },
            { label: '偶发卡顿定界', value: false },
          ]},
          { title: '远程优化', items: [
            { label: '远程优化触发时间', value: '定时' },
            { label: '远程WIFI信道切换', value: true },
            { label: '远程网关重启', value: true },
            { label: '远程WIFI功率调优', value: true },
          ]},
          { title: '差异化承载', items: [
            { label: '差异化承载', value: false },
          ]},
        ],
        planText: '',
        updatedAt: '',
      },
    }),
  ),

  // 图片资源 — 占位图
  http.get('/api/images/:imageId', ({ params }) => {
    const url = `https://placehold.co/1200x600/161B22/9CA3AF/png?text=${encodeURIComponent(
      String(params.imageId),
    )}`;
    return HttpResponse.redirect(url, 302);
  }),
];
