# Qwen OpenAI代理服务器 (Python版)

一个通过OpenAI兼容API端点公开Qwen模型的代理服务器，基于Python和FastAPI构建。

## 重要说明

当使用130,000到150,000个tokens或更多的上下文时，用户可能会遇到错误或504网关超时问题。这似乎是Qwen模型的实际限制。Qwen代码本身也往往在这个限制下出现问题并卡住。

## 快速开始

### 方法1: 直接运行

1. **前提条件**: 您需要与Qwen认证以生成所需的凭据文件。
   * 运行 `python authenticate.py` 进行Qwen账户认证
   * 这将在 `~/.qwen/oauth_creds.json` 中创建代理服务器所需的文件
   * 或者，您可以使用[QwenLM/qwen-code](https://github.com/QwenLM/qwen-code)官方`qwen-code` CLI工具

2. **安装依赖**:
   ```bash
   pip install -r requirements.txt
   ```

3. **启动服务器**:
   ```bash
   python main.py
   # 或者
   python run.py --host 0.0.0.0 --port 8080
   ```

4. **使用代理**: 将您的OpenAI兼容客户端指向 `http://localhost:8080/v1`。

### 方法2: Docker

1. **构建并运行**:
   ```bash
   docker-compose up -d
   ```

2. **首次认证** (容器运行后):
   ```bash
   # 进入容器
   docker exec -it qwen-openai-proxy-python bash
   
   # 运行认证
   python authenticate.py
   ```

## 多账户支持

代理支持多个Qwen账户以克服每个账户每天2,000次请求的限制。当达到配额限制时，账户会自动轮换。

### 设置多个账户

1. 列出现有账户:
   ```bash
   python authenticate.py list
   ```

2. 添加新账户:
   ```bash
   python authenticate.py add <账户ID>
   ```
   将 `<账户ID>` 替换为您账户的唯一标识符（例如：`account2`, `team-account`等）

3. 删除账户:
   ```bash
   python authenticate.py remove <账户ID>
   ```

### 账户轮换的工作原理

- 当您配置了多个账户时，代理将自动在它们之间轮换
- 每个账户有每天2,000次请求的限制
- 当账户达到限制时，Qwen的API将返回配额超出错误
- 代理检测这些配额错误并自动切换到下一个可用账户
- 请求计数在本地跟踪，并在UTC午夜每天重置
- 您可以通过以下方式检查所有账户的请求计数:
  ```bash
  python authenticate.py counts
  ```

### 账户使用监控

代理在终端提供实时反馈:
- 显示每个请求使用的账户
- 显示每个账户的当前请求计数
- 在由于配额限制而轮换账户时通知
- 指示在轮换期间下一个将尝试的账户

## 配置

代理服务器可以使用环境变量进行配置。在项目根目录中创建 `.env` 文件或直接在环境中设置变量。

* `LOG_FILE_LIMIT`: 保留的调试日志文件最大数量（默认：20）
* `DEBUG_LOG`: 设置为 `true` 启用调试日志（默认：false）
* `STREAM`: 设置为 `true` 启用流式响应（默认：false）
* `API_TIMEOUT`: API请求超时时间，秒（默认：300）
* `HOST`: 绑定地址（默认：localhost）
* `PORT`: 监听端口（默认：8080）

示例 `.env` 文件:
```bash
# 只保留最近的10个日志文件
LOG_FILE_LIMIT=10

# 启用调试日志（将创建日志文件）
DEBUG_LOG=true

# 启用流式响应（默认禁用）
STREAM=true

# API超时时间（5分钟）
API_TIMEOUT=300
```

## 使用示例

### Python (使用OpenAI库)

```python
import openai

client = openai.OpenAI(
    api_key="fake-key",  # 不使用，但OpenAI客户端需要
    base_url="http://localhost:8080/v1"
)

response = client.chat.completions.create(
    model="qwen3-coder-plus",
    messages=[
        {"role": "user", "content": "你好！"}
    ]
)

print(response.choices[0].message.content)
```

### cURL

```bash
curl -X POST "http://localhost:8080/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer fake-key" \
  -d '{
    "model": "qwen3-coder-plus",
    "messages": [
      {"role": "user", "content": "你好！"}
    ]
  }'
```

## 支持的端点

* `POST /v1/chat/completions` - 聊天完成
* `GET /v1/models` - 模型列表
* `POST /v1/embeddings` - 嵌入向量
* `POST /auth/initiate` - 启动认证流程
* `POST /auth/poll` - 轮询认证状态
* `GET /health` - 健康检查

## 测试

运行包含的测试脚本来验证功能:

```bash
# 运行所有测试
python test_api.py

# 运行特定测试
python test_api.py --test health
python test_api.py --test models
python test_api.py --test chat

# 测试不同的URL
python test_api.py --url http://localhost:8080
```

## Token计数

代理现在在终端中显示每个请求的token计数，显示输入tokens和API返回的使用统计（提示、完成和总tokens）。

## 致谢

本项目基于 [aptdnfapt/qwen-code-oai-proxy](https://github.com/aptdnfapt/qwen-code-oai-proxy) 的Node.js版本进行开发。感谢原作者提供了优秀的基础实现和设计思路。

### 主要改进

- **跨平台兼容性**: 从Node.js迁移到Python，解决了部分Linux环境下的兼容性问题
- **更好的适配性**: Python生态系统在不同操作系统上的适配性更高
- **现代化架构**: 使用FastAPI替代Express.js，提供更好的性能和开发体验
- **类型安全**: 采用Pydantic进行数据验证，提高代码可靠性
- **简化部署**: 优化了Docker配置和依赖管理

在保持原项目所有核心功能的基础上，Python版本提供了更好的稳定性和跨平台支持。

有关更详细的文档，请参阅 `docs/` 目录。
