/**
 * Vite 开发插件：将前端收到的 SSE 事件流写入本地文件。
 *
 * 监听 POST /dev/sse-log，body 为 { convId, events[] }，
 * 写入 frontend/data/sse_logs/{convId}_{timestamp}.json。
 * 仅在 dev server 中生效，生产构建无副作用。
 */

import fs from 'node:fs';
import path from 'node:path';
import type { Plugin, ViteDevServer } from 'vite';

const LOGS_DIR = path.resolve(__dirname, 'data/sse_logs');

export function sseLoggerPlugin(): Plugin {
  return {
    name: 'vite-plugin-sse-logger',
    configureServer(server: ViteDevServer) {
      fs.mkdirSync(LOGS_DIR, { recursive: true });

      server.middlewares.use('/dev/sse-log', (req, res) => {
        if (req.method !== 'POST') {
          res.writeHead(405).end();
          return;
        }
        const chunks: Buffer[] = [];
        req.on('data', (chunk: Buffer) => chunks.push(chunk));
        req.on('end', () => {
          try {
            const { convId, events } = JSON.parse(Buffer.concat(chunks).toString('utf-8'));
            const ts = new Date().toISOString().replace(/[:.]/g, '').slice(0, 15) + 'Z';
            const filename = `${convId}_${ts}.json`;
            fs.writeFileSync(
              path.join(LOGS_DIR, filename),
              JSON.stringify(events, null, 2),
              'utf-8',
            );
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ ok: true, file: filename }));
          } catch (e) {
            res.writeHead(500).end(String(e));
          }
        });
      });
    },
  };
}
