# AI_Hot_Events

GitHub 热点项目自动化监控服务。后端负责仓库采集、星标快照、热点榜单、项目画像、邮件日报和调度管理，前端提供 `/admin` 管理后台，用于在线维护配置和查看运行状态。

## 项目简介

这个项目围绕 GitHub 开源项目热度监控展开，核心链路是：

1. 配置监控源，发现新的候选仓库
2. 定时采集仓库信息和星标快照
3. 计算每日热点项目
4. 生成项目画像和邮件日报
5. 通过后台页面动态调整 GitHub、SMTP、LLM 和调度配置

后端启动时会从数据库加载可热更新配置，并在生命周期中启动调度器；前端构建后由 FastAPI 直接托管。

## 功能模块

- 仓库管理：新增、查询、更新 GitHub 仓库
- 监控源管理：维护 GitHub Search、Topic、Owner 等发现规则
- 星标快照：记录仓库 stars、forks、watchers 的历史变化
- 热点项目：按 24 小时和 7 日增长计算热点榜
- 项目画像：生成仓库摘要、功能点、受众和技术栈
- 邮件日报：生成并发送热点项目日报
- 调度管理：配置并重载定时任务
- 运行时配置：在线调整 GitHub、SMTP、LLM、榜单参数和总开关
- GitHub 运维：查看 API rate limit
- 健康检查：检查数据库连通性

## 技术栈

- 后端：FastAPI、SQLAlchemy、Pydantic Settings、APScheduler、PyMySQL
- 前端：Vue 3、Vite
- 数据库：MySQL 8.0+，推荐 utf8mb4
- 测试：pytest、FastAPI TestClient

## 目录结构

```text
app/        FastAPI 后端
frontend/   Vue 3 管理后台
tests/      pytest 测试
doc/        需求、接口、运维和建表脚本
doc/sql/数据库建表语句.sql  初始化表结构
```

## 快速开始

### 1. 准备数据库

先创建 MySQL 数据库，再执行 `doc/sql/数据库建表语句.sql` 初始化表结构。

### 2. 配置环境变量

项目使用 `.env` 读取启动配置。最少需要：

```env
APP_ENV=local
DEBUG=false
TIMEZONE=Asia/Shanghai
DATABASE_URL=mysql+pymysql://root:password@127.0.0.1:3306/ai_hot_events
API_AUTH_TOKEN=dev-admin-token
GITHUB_TOKEN=ghp_xxx
SCHEDULER_ENABLED=true
HOT_PROJECT_TOP_N=20
LOG_LEVEL=INFO
```

常用可选项：

- `SMTP_HOST`、`SMTP_PORT`、`SMTP_USERNAME`、`SMTP_PASSWORD`、`MAIL_FROM`
- `LLM_ENABLED`、`LLM_API_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`
- `GITHUB_API_BASE_URL`、`GITHUB_API_VERSION`

本地如果不想启用后台鉴权，可以不填 `API_AUTH_TOKEN`。

鉴权规则很简单：

- 配置了 `API_AUTH_TOKEN` 时，管理类接口需要 `Authorization: Bearer <token>`
- 没有配置 `API_AUTH_TOKEN` 时，本地会直接放行，方便联调和学习

### 3. 安装后端依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 4. 启动后端

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

启动后可访问：

- API 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/v1/health`
- 管理后台：`http://127.0.0.1:8000/admin`

### 5. 启动前端开发模式

```powershell
cd frontend
npm install
npm run dev
```

Vite 会把 `/api` 代理到 `http://127.0.0.1:8000`，方便本地联调。

### 6. 生产构建前端

```powershell
cd frontend
npm install
npm run build
cd ..
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

构建后，FastAPI 会直接托管 `frontend/dist`，`/admin` 即为前端入口。

## 主要接口

Base URL：`/api/v1`

- `GET /health`
- `GET /repositories`
- `POST /repositories`
- `PATCH /repositories/{repository_id}`
- `GET /monitor-sources`
- `POST /monitor-sources`
- `PATCH /monitor-sources/{source_id}`
- `DELETE /monitor-sources/{source_id}`
- `GET /star-snapshots?repository_id=...`
- `POST /star-snapshots/runs`
- `GET /hot-projects`
- `POST /hot-projects/runs`
- `GET /project-profiles/repositories/{repository_id}`
- `POST /project-profiles/runs`
- `GET /email-digests/subscribers`
- `POST /email-digests/subscribers`
- `POST /email-digests/runs`
- `GET /schedules`
- `PATCH /schedules/{schedule_id}`
- `POST /schedules/{schedule_id}/enable`
- `POST /schedules/{schedule_id}/disable`
- `POST /schedules/reload`
- `GET /jobs`
- `GET /github/rate-limit`
- `GET /admin/configs`
- `PUT /admin/configs`
- `POST /admin/configs/test-email`
- `POST /admin/configs/test-llm`

接口细节见 `doc/plan/接口文档.md`。

## 数据表

当前核心表包括：

- `repositories`
- `monitor_sources`
- `star_snapshots`
- `project_profiles`
- `hot_projects`
- `subscribers`
- `email_reports`
- `email_deliveries`
- `jobs`
- `schedules`
- `app_configs`

## 运维提示

- 后端会在启动时尝试加载数据库里的运行时配置
- `SCHEDULER_ENABLED=false` 可关闭后台调度器
- `frontend/dist` 是构建产物
- `frontend/node_modules` 不需要提交

## 相关文档

- `doc/plan/需求文档.md`
- `doc/plan/接口文档.md`
- `doc/sql/数据库建表语句.sql`
