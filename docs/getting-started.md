# 本地开发环境启动指南

## 环境要求

| 工具 | 版本要求 |
|---|---|
| Python | 3.11+ |
| Node.js | 18+ |
| pnpm | 8+（推荐）或 npm |
| uv（可选） | 最新版，依赖安装更快 |

---

## 目录结构

```
broadband-agent-demo/
├── backend/    # FastAPI 后端，端口 8080
└── frontend/   # Vite + React 前端，端口 5173
```

---

## 后端启动

### 1. 进入 backend 目录

```bash
cd backend
```

### 2. 安装依赖

**方式 A：uv（推荐，速度更快）**

```bash
uv sync
```

**方式 B：pip**

```bash
pip install -r requirements.txt
```

> `vendor/ce_insight_core` 是本地可编辑包，`uv sync` 会自动以 editable 模式安装；pip 方式已在 `requirements.txt` 末尾通过 `-e ./vendor/ce_insight_core` 处理。

### 3. 配置 API Key

后端通过 `configs/model.yaml` 读取模型配置，API Key 支持两种方式（任选其一）：

**方式 A：写入 `.env` 文件（推荐）**

在 `backend/` 目录下创建 `.env` 文件：

```bash
# backend/.env
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxx
```

**方式 B：直接写入 `configs/model.yaml`**

```yaml
api_key: "sk-or-v1-xxxxxxxxxxxx"
```

> `.env` 文件已在 `.gitignore` 中，不会提交到仓库。

### 4. 启动后端服务

```bash
# 使用 .env 文件时（推荐）
env $(cat .env | xargs) uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload

# 不使用 .env 文件时（api_key 已写入 model.yaml）
uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload
```

启动成功后终端输出：

```
INFO:     Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

### 5. 验证后端

```bash
curl http://localhost:8080/health
# 预期返回: {"status":"ok"}

curl http://localhost:8080/api/conversations
# 预期返回: {"code":0,"message":"success","data":{"list":[...]}}
```

---

## 前端启动

### 1. 进入 frontend 目录

```bash
cd frontend
```

### 2. 安装依赖

```bash
pnpm install
```

### 3. 启动开发服务器

```bash
pnpm dev
```

启动成功后终端输出：

```
  VITE v5.x  ready in xxx ms

  ➜  Local:   http://localhost:5173/
```

前端通过 Vite 代理将 `/api/*` 请求转发到 `http://localhost:8080`，无需额外配置跨域。

---

## 常见问题

### 前端请求返回 500 / ERR_CONNECTION_REFUSED

后端未启动，或端口不匹配。确认后端运行在 **8080** 端口，并检查 `frontend/vite.config.ts` 中代理目标是否为 `http://localhost:8080`。

### `ModuleNotFoundError: No module named 'cv2'`

WIFI 仿真 skill 依赖 OpenCV，安装方式：

```bash
pip install opencv-python-headless
```

### API Key 不生效 / 模型调用失败

检查优先级：`configs/model.yaml` 中的 `api_key` 字段 > 环境变量 `OPENROUTER_API_KEY`。确认启动命令前缀了 `env $(cat .env | xargs)`（如果使用 `.env` 文件）。

### 数据库路径

后端运行时自动在 `backend/data/` 下创建两个 SQLite 数据库：

- `api.db`：会话与消息数据（前端展示用）
- `sessions.db`：agno 会话轨迹（可观测性用）

如需重置数据，直接删除 `backend/data/` 目录下的 `.db` 文件后重启即可。

---

## 端口一览

| 服务 | 地址 |
|---|---|
| 前端（Vite Dev） | http://localhost:5173 |
| 后端（FastAPI） | http://localhost:8080 |
| 后端健康检查 | http://localhost:8080/health |
