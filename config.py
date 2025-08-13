"""Configuration module for Qwen OpenAI Proxy."""

import os
from typing import Optional
from pydantic import BaseModel
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class QwenConfig(BaseModel):
    """Qwen OAuth configuration."""
    client_id: str = os.getenv('QWEN_CLIENT_ID', 'f0304373b74a44d2b584a3fb70ca9e56')
    client_secret: str = os.getenv('QWEN_CLIENT_SECRET', '')
    base_url: str = os.getenv('QWEN_BASE_URL', 'https://chat.qwen.ai')
    device_code_endpoint: str = os.getenv('QWEN_DEVICE_CODE_ENDPOINT', 'https://chat.qwen.ai/api/v1/oauth2/device/code')
    token_endpoint: str = os.getenv('QWEN_TOKEN_ENDPOINT', 'https://chat.qwen.ai/api/v1/oauth2/token')
    scope: str = os.getenv('QWEN_SCOPE', 'openid profile email model.completion')


class Config(BaseModel):
    """应用程序配置."""
    
    # 服务器配置
    port: int = int(os.getenv('PORT', '8080'))
    host: str = os.getenv('HOST', 'localhost')
    
    # 流式配置
    stream: bool = os.getenv('STREAM', 'false').lower() == 'true'
    
    # Qwen配置
    qwen: QwenConfig = QwenConfig()
    
    # 默认模型
    default_model: str = os.getenv('DEFAULT_MODEL', 'qwen3-coder-plus')
    
    # Token刷新缓冲时间（毫秒）
    token_refresh_buffer: int = int(os.getenv('TOKEN_REFRESH_BUFFER', '30000'))
    
    # 调试日志配置
    debug_log: bool = os.getenv('DEBUG_LOG', 'false').lower() == 'true'
    log_file_limit: int = int(os.getenv('LOG_FILE_LIMIT', '20'))
    
    # API超时时间（秒）
    api_timeout: int = int(os.getenv('API_TIMEOUT', '300'))  # 5分钟
    
    # 默认API端点
    default_api_base_url: str = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
    
    # API认证配置
    api_key: Optional[str] = os.getenv('API_KEY')  # 用于保护代理服务器的API Key


# 创建全局配置实例
config = Config()