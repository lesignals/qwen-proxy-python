"""数据模型定义."""

from typing import List, Optional, Any, Dict, Union
from pydantic import BaseModel, Field
from datetime import datetime


class Message(BaseModel):
    """聊天消息模型."""
    role: str
    content: str
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    """聊天完成请求模型."""
    model: str = "qwen3-coder-plus"
    messages: List[Message]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    stream: Optional[bool] = False
    stream_options: Optional[Dict[str, Any]] = None


class EmbeddingRequest(BaseModel):
    """嵌入向量请求模型."""
    model: str = "text-embedding-v1"
    input: Union[str, List[str]]


class QwenCredentials(BaseModel):
    """Qwen认证凭据模型."""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    resource_url: Optional[str] = None
    expiry_date: Optional[int] = None


class DeviceFlowResponse(BaseModel):
    """设备授权流程响应模型."""
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int
    code_verifier: str


class TokenResponse(BaseModel):
    """Token响应模型."""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: int
    resource_url: Optional[str] = None


class Usage(BaseModel):
    """Token使用统计模型."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatChoice(BaseModel):
    """聊天选择模型."""
    index: int
    message: Message
    finish_reason: Optional[str] = None


class ChatCompletionResponse(BaseModel):
    """聊天完成响应模型."""
    id: str
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(datetime.now().timestamp()))
    model: str
    choices: List[ChatChoice]
    usage: Optional[Usage] = None


class StreamChoice(BaseModel):
    """流式聊天选择模型."""
    index: int
    delta: Dict[str, Any]
    finish_reason: Optional[str] = None


class ChatCompletionStreamResponse(BaseModel):
    """流式聊天完成响应模型."""
    id: str
    object: str = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(datetime.now().timestamp()))
    model: str
    choices: List[StreamChoice]
    usage: Optional[Usage] = None


class EmbeddingData(BaseModel):
    """嵌入向量数据模型."""
    object: str = "embedding"
    embedding: List[float]
    index: int


class EmbeddingResponse(BaseModel):
    """嵌入向量响应模型."""
    object: str = "list"
    data: List[EmbeddingData]
    model: str
    usage: Optional[Usage] = None


class ModelData(BaseModel):
    """模型数据模型."""
    id: str
    object: str = "model"
    created: int = 1754686206
    owned_by: str = "qwen"


class ModelsResponse(BaseModel):
    """模型列表响应模型."""
    object: str = "list"
    data: List[ModelData]


class ErrorDetail(BaseModel):
    """错误详情模型."""
    message: str
    type: str


class ErrorResponse(BaseModel):
    """错误响应模型."""
    error: ErrorDetail