# 基于 RAG 与 LangGraph 的智能知识库问答与文档生成系统

## 项目简介

本项目是一个面向毕业设计场景实现的智能知识库系统，题目为 **“基于 RAG 与 LangGraph 的智能知识库问答与文档生成系统”**。系统围绕本地资料管理、检索增强生成、智能问答、文档起草、格式化导出和后台知识库管理展开，目标是将非结构化文档、表格数据和大语言模型能力整合为一套可运行、可扩展、可演示的 Web 应用。

项目核心位于 `Agent/` 目录，后端采用 Flask 提供统一 Web 服务，前端采用原生 HTML/CSS/JavaScript 与 SSE 流式交互。聊天主链路通过 `ChatGraphRuntime` 组织请求处理流程，默认使用 LangGraph 编排图运行；知识库检索采用 FAISS 语义检索、BM25 关键词检索与 RRF 融合排序；文档生成流程采用多 Agent 协作方式，覆盖规划、检索、写作、审查和反思等环节。

本仓库不包含真实业务资料、运行数据库、向量索引或 API Key。知识库内容需要在本地使用示例材料重新构建。

## 主要功能

- **登录认证与权限控制**：支持用户登录、管理员账户、角色和部门权限过滤。
- **智能问答**：基于 `/api/chat` 提供 SSE 流式回答，支持知识库问答、身份问答和澄清追问。
- **RAG 检索增强生成**：结合 FAISS、BM25、RRF 和来源元数据，提高回答的相关性与可追溯性。
- **文档生成**：支持通知、报告、说明、请示等文本材料的起草、改写、审查和格式化。
- **知识库管理**：支持文件上传、解析、切分、入库、重建索引、审计和健康检查。
- **表格处理**：支持结构化表格解析、筛选排序、数值校验和 Excel 导出。
- **后台任务**：使用 SQLite 保存任务状态，使用本地线程池执行轻量异步任务。
- **导出能力**：支持 Word、Excel 等常见办公文档导出。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 后端框架 | Flask、Jinja2、Flask-CORS |
| 前端交互 | HTML、CSS、JavaScript、Server-Sent Events |
| 编排框架 | LangGraph、内部 `ChatGraphRuntime`、多 Agent 服务层 |
| 大模型接口 | DeepSeek API，兼容 OpenAI SDK 调用方式 |
| 联网搜索 | 博查 Web Search API |
| 向量检索 | sentence-transformers、FAISS |
| 关键词检索 | jieba、rank-bm25 |
| 融合排序 | RRF（Reciprocal Rank Fusion） |
| 文档处理 | python-docx、PyMuPDF、openpyxl、pandas |
| 数据存储 | SQLite、本地文件系统 |
| 部署方式 | Docker、gunicorn |

## 系统架构

```text
用户浏览器
  -> Flask 路由层 routes/
  -> AppContext 运行期依赖容器
  -> ChatGraphRuntime
  -> TaskPlanner / IntentRouter
  -> ToolOrchestrator / Stream Service
  -> KnowledgeAgent / Document Agent / Export Service
  -> FAISS + BM25 + SQLite + 本地文件存储
```

### 聊天主链路

```text
POST /api/chat
  -> routes/chat_routes.py
  -> context.chat_runtime().stream(...)
  -> ChatGraphRuntime
  -> TaskPlanner
  -> ToolOrchestrator
  -> SSE stream
```

`CHAT_RUNTIME` 默认值为 `langgraph`。当 LangGraph 可用时，系统使用图编排方式处理请求；当运行环境缺少 LangGraph 或显式切换为 legacy 时，可回退到规则化意图路由。

### RAG 检索链路

```text
用户问题
  -> 查询改写与任务规划
  -> BM25 关键词召回
  -> FAISS 向量召回
  -> RRF 融合排序
  -> 权限过滤与来源整理
  -> 大模型生成回答
```

知识库索引文件不提交到仓库，需要通过本地资料重新构建。当前仓库保留索引构建、检索、上传和管理代码。

### 文档生成链路

```text
用户需求
  -> PlannerAgent 任务规划
  -> SearchAgent 可选联网搜索
  -> KnowledgeAgent 本地知识检索
  -> WriterAgent 正文生成
  -> ReviewerAgent 质量审查
  -> ReflectionAgent 复杂任务反思
  -> Word/Excel 导出
```

文档子流程支持 LangGraph 图运行，也保留线性 runner 作为兼容方案。

## 目录结构

```text
.
├── Agent/
│   ├── app.py                         # Flask 应用入口
│   ├── app_dependencies.py            # 启动依赖装配
│   ├── app_context.py                 # 运行期上下文与 service factory
│   ├── routes/                        # 页面、认证、聊天、上传、后台、导出路由
│   ├── chat_runtime.py                # 聊天主运行时
│   ├── chat_container.py              # 聊天服务懒加载装配
│   ├── task_planner.py                # 工具化任务规划
│   ├── tool_runtime.py                # 工具执行与 SSE 事件整合
│   ├── agents/                        # 多 Agent 实现
│   ├── knowledge_base/                # 知识库核心代码与空配置
│   ├── templates/                     # Web 页面模板
│   ├── static/                        # 前端 JS/CSS
│   ├── docs/                          # 架构与优化文档
│   └── 智能知识库平台毕业设计PRD.md     # 毕业设计需求说明
├── uv-agent/                          # 辅助实验工程
├── test_system.py                     # 系统级检查脚本
└── README.md                          # 项目说明
```

## 快速开始

### 1. 创建环境

```bash
cd Agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

按需填写：

```text
JWT_SECRET=generate-a-random-secret-here
DEEPSEEK_API_KEY=sk-your-deepseek-key-here
BOCHA_API_KEY=sk-your-bocha-key-here
CHAT_RUNTIME=langgraph
```

### 3. 启动服务

```bash
python app.py --port 5003
```

访问地址：

- 登录页：`http://localhost:5003/login`
- 聊天页：`http://localhost:5003/chat`
- 管理后台：`http://localhost:5003/admin`
- 健康检查：`http://localhost:5003/api/health`

## 知识库构建

仓库默认不包含任何真实知识库资料或向量索引。可将示例文档放入本地资料目录后执行：

```bash
cd Agent
python builder.py --input ./知识库 --output ./knowledge_base
```

构建完成后会生成 FAISS 索引和元数据文件。此类运行产物已加入 `.gitignore`，不建议提交到公开仓库。

## 测试与验证

基础语法检查：

```bash
cd Agent
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp python3 -m py_compile \
  app.py app_config.py app_context.py app_dependencies.py \
  routes/*.py chat_runtime.py chat_container.py job_service.py upload_service.py \
  chat_rag.py chat_lightweight.py chat_answer_quality.py agents/*.py
```

安装测试依赖后可运行：

```bash
python -m pytest
```

部分外部 API 测试需要配置真实 Key，并通过环境变量显式开启。

## 脱敏与数据说明

本公开仓库仅保留系统源码、架构文档和毕业设计说明，不包含：

- 真实机构名称或真实人员信息
- 真实业务文档、合同、报表或演示材料
- SQLite 运行数据库
- FAISS 向量索引、文本切片和元数据缓存
- API Key、Token、Cookie 或私有配置

如需演示系统效果，请使用公开可用的示例文档自行构建知识库。

## 毕业设计亮点

- 将 RAG 检索增强生成应用于本地知识库问答与文档写作场景。
- 使用 LangGraph 和多 Agent 思路组织复杂任务流程。
- 同时支持语义检索、关键词检索和融合排序，兼顾召回率与准确性。
- 采用 SSE 流式输出改善大模型生成过程中的等待体验。
- 后台管理、异步任务、导出能力和权限过滤较完整，具备工程化展示价值。

## 许可证

本项目用于毕业设计与学习展示，可根据学校要求补充开源许可证。
