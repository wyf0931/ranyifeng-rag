# 阮一峰科技爱好者周刊 RAG 系统

基于 SQLite FTS5 + jieba + LangGraph 的简洁 RAG 系统，用于搜索阮一峰科技爱好者周刊。

## 技术栈

- **后端**: Flask + SQLModel + Pydantic
- **数据库**: SQLite FTS5 + jieba 中文分词
- **AI**: LangGraph + LangChain + OpenAI SDK
- **前端**: Tailwind CSS + Alpine.js + Lucide icons
- **包管理**: uv

## 功能特点

- 🔍 **智能搜索**: 基于 FTS5 全文检索，支持 jieba 中文分词
- 🤖 **AI 问答**: ReAct 模式的 RAG 流程，支持查询重写和多轮思考
- 📊 **流程透明**: 完整显示查询重写、思考过程、引用来源
- 📚 **数据导入**: 支持从 JSON 文件批量导入，幂等性保证
- 🔄 **索引重建**: 支持在更新 jieba 词典后重建索引

## 快速开始

### 1. 环境准备

```bash
# 安装 uv（如果尚未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 克隆项目
cd ruanyifeng-rag
```

### 2. 安装依赖

```bash
# 同步依赖
uv sync

# 复制环境配置
cp .env.example .env
# 根据需要修改 .env 文件
```

### 3. 运行应用

```bash
# 方式1：直接运行
uv run python run.py

# 方式2：使用运维脚本
./bin/ops.sh start
./bin/ops.sh status
./bin/ops.sh logs
```

访问 http://127.0.0.1:5000 开始使用。

### 4. 导入数据

```bash
# 方式1：通过管理页面导入
访问 http://127.0.0.1:5000/admin

# 方式2：通过 API 导入
curl -X POST http://127.0.0.1:5000/api/import \
  -H "Content-Type: application/json" \
  -d '{"path": "data/article-example.json"}'

# 方式3：批量导入目录
curl -X POST http://127.0.0.1:5000/api/import \
  -H "Content-Type: application/json" \
  -d '{"path": "data/articles"}'
```

### 5. 重建索引

在更新 `data/jieba_custom.dict` 后，重建索引：

```bash
# 方式1：通过管理页面
访问 http://127.0.0.1:5000/admin

# 方式2：通过 API
curl -X POST http://127.0.0.1:5000/api/reindex
```

## 项目结构

```
ruanyifeng-rag/
├── app/
│   ├── __init__.py         # Flask 应用工厂
│   ├── config.py           # 配置管理
│   ├── models/             # 数据模型
│   │   ├── article.py      # 文章模型
│   │   └── item.py         # 条目模型
│   ├── services/           # 业务逻辑
│   │   ├── database.py     # 数据库服务
│   │   ├── import_service.py  # 导入服务
│   │   └── rag_service.py  # RAG 服务
│   ├── routes/             # 路由
│   │   ├── chat.py         # 聊天页面
│   │   └── api.py          # API 接口
│   └── templates/          # 模板
│       ├── chat.html       # 聊天页面
│       └── admin.html      # 管理页面
├── bin/
│   └── ops.sh              # 运维脚本
├── data/
│   ├── articles/           # 文章数据目录
│   ├── article-example.json # 示例数据
│   └── rag.db              # SQLite 数据库（自动生成）
├── tests/                  # 测试
├── pyproject.toml          # 项目配置
├── run.py                  # 入口文件
└── README.md
```

## 运维命令

```bash
./bin/ops.sh start    # 启动服务
./bin/ops.sh stop     # 停止服务
./bin/ops.sh restart  # 重启服务
./bin/ops.sh status   # 查看状态
./bin/ops.sh logs     # 查看日志
```

## API 接口

### POST /api/query
RAG 查询接口

```json
{
  "query": "如何使用 macOS 内置的 OCR 功能？"
}
```

### POST /api/import
导入数据接口

```json
{
  "path": "data/articles"
}
```

### POST /api/reindex
重建索引接口

### GET /api/stats
获取统计信息

## 数据格式

文章 JSON 格式参考 `data/article-example.json`：

```json
{
  "title": "科技爱好者周刊（第 302 期）",
  "link": "https://www.ruanyifeng.com/blog/2024/05/weekly-issue-302.html",
  "number": "302",
  "sections": [
    {
      "name": "封面图",
      "items": [
        {
          "title": "形似灯笼的稻田塔",
          "link": "https://...",
          "description": "描述文本",
          "user": null,
          "user_link": null,
          "images": ["https://..."]
        }
      ]
    }
  ]
}
```

## 开发指南

### 添加自定义分词

编辑 `data/jieba_custom.dict`：

```
科技爱好者周刊 5 n
阮一峰 5 nr
```

然后重建索引。

### 扩展 RAG 流程

编辑 `app/services/rag_service.py`，修改 LangGraph 工作流。

## 许可证

MIT
