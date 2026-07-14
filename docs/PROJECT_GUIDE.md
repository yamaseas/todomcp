# SQLite Todo MCP Demo 项目说明

## 1. 项目目标

本项目是一个用于学习 Model Context Protocol（MCP）的完整小型示例。它把一个
SQLite 待办事项应用封装成 MCP Server，使 Codex、其他 Agent Host 或普通 MCP
Client 能够通过统一协议发现并使用待办管理能力。

项目重点不是实现复杂的待办系统，而是展示以下问题：

- 如何使用 Python 创建 MCP Server；
- 如何通过 Tool、Resource 和 Prompt 暴露能力；
- MCP Client 如何发现并调用 Server；
- 如何通过 stdio 在 Client 与 Server 之间传输 MCP 消息；
- 如何把 MCP 协议代码与普通业务代码分离；
- 如何测试数据库逻辑和 MCP 协议交互。

## 2. 总体架构

项目分为四个主要部分：

```text
┌─────────────────────────────────────────────────────────┐
│ Codex、其他 Agent Host 或示例 Client                    │
│ - 理解用户意图                                          │
│ - 发现 MCP 能力                                         │
│ - 选择并调用 Tool、读取 Resource 或获取 Prompt          │
└─────────────────────────┬───────────────────────────────┘
                          │ MCP over stdio
                          ▼
┌─────────────────────────────────────────────────────────┐
│ MCP Server：server.py                                   │
│ - 声明 Server instructions                              │
│ - 暴露 Tools、Resource、Prompt                          │
│ - 将协议调用转发给 Repository                           │
└─────────────────────────┬───────────────────────────────┘
                          │ 普通 Python 方法调用
                          ▼
┌─────────────────────────────────────────────────────────┐
│ 业务与持久化层：repository.py                           │
│ - 数据模型与参数约束                                    │
│ - 待办 CRUD                                              │
│ - SQLite 查询和事务                                     │
└─────────────────────────┬───────────────────────────────┘
                          │ SQL
                          ▼
                     SQLite 数据库
```

这种结构将协议层和业务层分开。`repository.py` 不依赖 MCP，因此可以脱离 Agent
独立测试或复用于其他接口；`server.py` 只负责把已有业务能力转换成 MCP 能力。

## 3. 目录结构

```text
mcp-todo-demo/
├── src/mcp_todo/
│   ├── __init__.py
│   ├── server.py          # MCP Server 与协议能力声明
│   ├── client.py          # stdio MCP Client 演示
│   └── repository.py      # 数据模型、业务逻辑与 SQLite 持久化
├── tests/
│   ├── test_repository.py # 数据层单元测试
│   └── test_mcp_server.py # MCP Client/Server 集成测试
├── docs/
│   └── PROJECT_GUIDE.md   # 本文档
├── pyproject.toml         # 项目元数据、依赖、命令入口与测试配置
├── uv.lock                # uv 生成的精确依赖锁文件
├── README.md              # 快速开始和常用命令
└── .gitignore
```

## 4. MCP Server

MCP Server 位于 `src/mcp_todo/server.py`，使用官方 Python SDK 中的 `FastMCP`
实现。

### 4.1 Server 初始化

```python
mcp = FastMCP(
    "SQLite Todo Demo",
    instructions=(
        "Manage a local todo list. Use list_todos before changing an existing item "
        "so that you have its numeric id."
    ),
)
```

这里定义了：

- Server 名称 `SQLite Todo Demo`；
- Server 级别的 `instructions`；
- instructions 告诉 Agent 该 Server 用于管理待办，并建议修改任务前先查询 ID。

Codex 连接 Server 后会读取这些元数据，再结合各个工具的名称、docstring 和参数
Schema 判断何时使用它们。用户通常只需要说“添加一个待办”，不需要显式指定
`add_todo`。

### 4.2 数据库选择

```python
def get_repository() -> TodoRepository:
    return TodoRepository(
        os.environ.get("MCP_TODO_DB", str(DEFAULT_DATABASE))
    )
```

数据库路径通过 `MCP_TODO_DB` 环境变量配置。如果没有提供，则默认使用当前工作目录
下的 `data/todos.db`。每次工具调用都会获得一个指向同一数据库文件的 Repository，
SQLite 文件负责保存跨调用的数据状态。

### 4.3 Tools

Tool 表示 Agent 可以主动执行的操作。`@mcp.tool()` 会让 FastMCP 根据函数签名、
类型注解和 docstring 自动生成工具描述与 JSON Schema。

本项目提供四个 Tool：

| Tool | 参数 | 返回值 | 功能 |
|---|---|---|---|
| `add_todo` | `title`、`description`、`priority` | `Todo` | 新建待办 |
| `list_todos` | `status` | `list[Todo]` | 查询全部或指定状态的待办 |
| `complete_todo` | `todo_id` | `Todo` | 将指定待办标记为已完成 |
| `delete_todo` | `todo_id` | `bool` | 永久删除指定待办 |

例如：

```python
@mcp.tool()
def add_todo(
    title: str,
    description: str = "",
    priority: Priority = "medium",
) -> Todo:
    """Create a todo item and return the stored item with its generated id."""
    return get_repository().add(title, description, priority)
```

其中 `Priority` 被定义为：

```python
Literal["low", "medium", "high"]
```

因此 MCP SDK 生成的参数 Schema 只允许这三个值。如果 Client 传入 `urgent`，请求会
在协议参数校验阶段返回错误。

### 4.4 Resource

Resource 用于提供可读取的上下文数据。本项目提供：

```text
todo://stats
```

它返回如下 JSON 文本：

```json
{
  "total": 3,
  "pending": 2,
  "completed": 1
}
```

实现代码调用 Repository 的聚合查询，然后将 Pydantic 模型序列化为 JSON：

```python
@mcp.resource("todo://stats")
def todo_stats() -> str:
    return json.dumps(
        get_repository().stats().model_dump(),
        ensure_ascii=False,
    )
```

Tool 通常表示“执行动作”，Resource 通常表示“读取数据”。统计信息也可以实现为
Tool，但用 Resource 能展示 MCP 对上下文读取的标准化支持。

### 4.5 Prompt

Prompt 是 Server 提供的可复用提示模板。本项目提供 `daily_review`：

```python
@mcp.prompt()
def daily_review(focus: str = "today") -> str:
    return (
        f"Review my {focus} tasks. First call list_todos with status='pending', "
        "then group the results by priority and propose an execution order."
    )
```

它不直接访问数据库，而是生成一段指导 Agent 工作的提示词：先查询未完成任务，再按
优先级整理并提出执行顺序。`focus` 参数可以把模板调整为今天、本周或其他范围。

### 4.6 stdio 传输

Server 入口使用：

```python
mcp.run(transport="stdio")
```

stdio 模式下，Codex 或 MCP Client 启动 Server 子进程，并通过进程的标准输入和标准
输出交换 MCP 消息。它不需要监听端口，也不需要提供 HTTP URL，适合本地开发工具。

需要注意：stdout 属于协议通信通道，Server 不应随意向 stdout 打印普通日志，否则
可能破坏 MCP 消息。日志应写到 stderr 或使用 SDK 提供的日志机制。

## 5. 数据模型与 SQLite Repository

数据层位于 `src/mcp_todo/repository.py`。

### 5.1 Pydantic 模型

`Todo` 描述单条待办：

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | `int` | SQLite 自动生成的主键 |
| `title` | `str` | 待办标题 |
| `description` | `str` | 可选详细说明 |
| `priority` | `low / medium / high` | 优先级 |
| `status` | `pending / completed` | 完成状态 |
| `created_at` | `str` | UTC ISO 8601 创建时间 |
| `completed_at` | `str \| None` | UTC ISO 8601 完成时间 |

`TodoStats` 描述总数、未完成数和已完成数。

这些模型同时承担三项职责：

1. 校验从 SQLite 读取的数据；
2. 明确 Python 业务层的返回类型；
3. 帮助 FastMCP 生成结构化 MCP 返回 Schema。

### 5.2 数据库初始化

实例化 `TodoRepository` 时会：

1. 保存数据库文件路径；
2. 自动创建数据库父目录；
3. 执行 `CREATE TABLE IF NOT EXISTS`。

表结构在数据库层也设置了约束：

- `title` 不能为空；
- `priority` 只能是 `low`、`medium` 或 `high`；
- `status` 只能是 `pending` 或 `completed`；
- `id` 使用 SQLite 自增主键。

类型注解负责协议入口校验，SQLite CHECK 约束负责最终持久化保护，形成两层校验。

### 5.3 CRUD 实现

`add()` 会清理标题和描述两端的空格，拒绝空标题，写入 UTC 创建时间，并返回刚刚
插入的完整记录。

`list()` 根据 `status` 动态增加 `WHERE status = ?`，然后按 ID 排序。SQL 参数通过
占位符绑定，避免把用户输入直接拼接进 SQL。

`complete()` 更新状态和完成时间。如果 `UPDATE` 没有影响任何记录，则抛出
`ValueError`，说明 ID 不存在。

`delete()` 删除指定记录，并用相同方式处理不存在的 ID。

`stats()` 使用条件聚合在一条 SQL 中计算三个统计值：

```sql
SELECT
    COUNT(*) AS total,
    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed
FROM todos
```

数据库为空时，SQLite 的 `SUM` 可能返回 `NULL`，代码使用 `or 0` 将其标准化为整数
零。

## 6. 示例 MCP Client

`src/mcp_todo/client.py` 是一个不依赖大模型的 Client 示例。它用于展示 MCP Client
如何以编程方式使用 Server，也便于验证协议链路。

### 6.1 启动 Server 子进程

Client 创建 `StdioServerParameters`：

```python
parameters = StdioServerParameters(
    command=sys.executable,
    args=["-m", "mcp_todo.server"],
    env=environment,
)
```

这会使用当前虚拟环境中的 Python 启动 `mcp_todo.server`，并通过环境变量把数据库
路径传给子进程。

### 6.2 建立会话

```python
async with stdio_client(parameters) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
```

`stdio_client` 管理 Server 子进程和 stdio 流，`ClientSession` 管理 MCP 会话，
`initialize()` 完成协议初始化和能力协商。

### 6.3 演示流程

Client 依次执行：

1. `list_tools()`：发现 Server 暴露的所有 Tool；
2. `call_tool("add_todo", ...)`：创建高优先级待办；
3. `call_tool("list_todos", ...)`：查询未完成待办；
4. `call_tool("complete_todo", ...)`：完成刚创建的待办；
5. `read_resource("todo://stats")`：读取统计 Resource。

工具结果的 `structuredContent` 字段包含结构化返回值，Client 不需要解析面向人类的
文本。

默认情况下 Client 使用临时数据库，进程结束后自动清理；传入 `--db` 可以保留数据：

```bash
uv run mcp-todo-client --db ./data/demo.db
```

## 7. 项目配置与命令入口

`pyproject.toml` 定义了两个命令：

```toml
[project.scripts]
mcp-todo-server = "mcp_todo.server:main"
mcp-todo-client = "mcp_todo.client:main"
```

安装依赖后，可以直接运行：

```bash
uv run mcp-todo-server
uv run mcp-todo-client
```

主要运行依赖是 `mcp>=1.28,<2`。`<2` 用于避免项目在 MCP Python SDK 2.x
预发布或大版本切换时意外获得不兼容接口。开发依赖中包含 `pytest`。

## 8. Codex 中的配置

该 Server 是本地 STDIO Server。在 Codex 配置界面中可以填写：

| 配置项 | 值 |
|---|---|
| Name | `todo` |
| Type | `STDIO` |
| Command | `/home/ovo/.local/bin/uv` |
| Argument 1 | `run` |
| Argument 2 | `mcp-todo-server` |
| Environment Key | `MCP_TODO_DB` |
| Environment Value | `/home/ovo/se/mcp-todo-demo/data/todos.db` |
| Working directory | `/home/ovo/se/mcp-todo-demo` |

保存并重启 Codex 后，可以直接使用自然语言：

```text
添加一个高优先级待办：完成 MCP 项目说明。
```

Codex 会根据 Server instructions、Tool 名称、docstring 和参数 Schema 判断是否调用
`add_todo`。显式说出 Server 名称或 Tool 名称不是正常使用的必要条件。

## 9. 测试设计

项目包含两层测试。

### 9.1 Repository 单元测试

`tests/test_repository.py` 使用 pytest 的 `tmp_path` 为每个测试创建隔离的临时 SQLite
数据库，覆盖：

- 创建和查询待办；
- 状态过滤；
- 完成待办和统计结果；
- 删除待办；
- 完成或删除不存在的 ID；
- 拒绝空标题。

这些测试不启动 MCP Server，因此失败时容易定位为数据或业务逻辑问题。

### 9.2 MCP 集成测试

`tests/test_mcp_server.py` 使用 MCP SDK 提供的
`create_connected_server_and_client_session` 创建内存 Client/Server 会话。它不启动
外部子进程，但会经过真实 MCP 消息、Schema 校验和 Server 分发逻辑。

测试覆盖：

- Server 是否正确声明四个 Tools；
- `todo://stats` Resource 是否可发现；
- `daily_review` Prompt 是否可发现；
- 创建、查询、完成任务能否通过 MCP 往返；
- Resource 返回的统计是否正确；
- 非法优先级是否被转换为 MCP 协议错误。

运行全部测试：

```bash
uv run pytest
```

## 10. 当前功能清单

- 使用自然语言驱动的待办创建能力；
- 待办标题、描述和三级优先级；
- 查询全部、未完成或已完成待办；
- 标记任务完成并记录完成时间；
- 永久删除待办；
- 读取任务总数和状态统计；
- 获取每日任务回顾 Prompt；
- SQLite 本地持久化；
- 自定义数据库路径；
- MCP 结构化输入和输出；
- stdio Client/Server 通信；
- Codex MCP 集成；
- Repository 单元测试与 MCP 集成测试。

## 11. 设计特点与局限

### 设计特点

- **关注点分离**：MCP 协议代码不进入 Repository；
- **类型驱动**：类型注解同时服务于 Python、Pydantic 和 MCP Schema；
- **零外部数据库服务**：SQLite 文件开箱即用；
- **可测试性**：业务层和协议层可以分别验证；
- **可移植性**：任何兼容 MCP 的 Client 都可以调用 Server。

### 当前局限

- 没有用户和权限模型，连接同一数据库的 Client 共享全部数据；
- 没有任务截止时间、标签、修改标题或恢复未完成等功能；
- SQLite 同步访问适合演示和轻量使用，不适合高并发远程服务；
- 当前只提供 stdio 传输，没有部署 Streamable HTTP 服务；
- Prompt 的 `focus` 只影响提示文本，没有直接用于数据库日期过滤；
- 删除操作没有软删除或撤销机制。

这些限制是刻意保留的，使项目能够集中展示 MCP 的核心结构。后续可以在不改变 MCP
Client 使用方式的前提下扩展 Repository 和新增 Tools。
