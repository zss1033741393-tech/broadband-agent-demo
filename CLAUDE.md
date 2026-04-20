# broadband-agent-demo

Fork of [huangxn27/broadband-agent-demo](https://github.com/huangxn27/broadband-agent-demo).

## 开发规范

- **开发分支**: `dev` (跟踪 `origin/dev`)
- **推送目标**: 所有代码更新推送至远程 `dev` 分支

## 仓库结构

- `frontend/` - 前端代码
- `backend/` - 通过 git subtree 接入，源仓库为 [zss1033741393-tech/broadband-agent](https://github.com/zss1033741393-tech/broadband-agent) 的 `dev` 分支
- `docs/` - 文档

## Git Subtree (backend)

backend 目录通过 git subtree 管理，remote 名为 `backend-upstream`。

拉取最新 backend 代码:
```bash
git subtree pull --prefix=backend backend-upstream dev --squash
```

推送 backend 改动回上游:
```bash
git subtree push --prefix=backend backend-upstream dev
```

## Git 远程配置

- `origin`: https://github.com/zss1033741393-tech/broadband-agent-demo.git
- `backend-upstream`: https://github.com/zss1033741393-tech/broadband-agent.git
