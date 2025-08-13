"""Qwen OpenAI代理服务器主入口."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Union, Dict, Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from models import (
    ChatCompletionRequest,
    EmbeddingRequest,
    ErrorResponse,
    ErrorDetail
)
from qwen.api import QwenAPI
from qwen.auth import QwenAuthManager
from utils.logger import DebugLogger
from utils.token_counter import count_tokens
from config import config


# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 认证配置
security = HTTPBearer(auto_error=False)

# 全局实例
qwen_api = QwenAPI()
auth_manager = QwenAuthManager()
debug_logger = DebugLogger()


async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """验证Authorization header中的token."""
    # 如果没有配置API Key，则跳过认证
    if not config.api_key:
        logger.warning("未配置API_KEY环境变量，认证功能已禁用")
        return None
        
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要提供API Key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if credentials.credentials != config.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的API Key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用程序生命周期管理."""
    # 启动时
    logger.info(f"Qwen OpenAI代理服务器启动于 http://{config.host}:{config.port}")
    logger.info(f"OpenAI兼容端点: http://{config.host}:{config.port}/v1")
    logger.info(f"认证端点: http://{config.host}:{config.port}/auth/initiate")
    
    # 显示可用账户
    try:
        await qwen_api.auth_manager.load_all_accounts()
        await qwen_api.auth_manager.load_request_counts()  # 加载请求计数
        account_ids = qwen_api.auth_manager.get_account_ids()
        
        print(f'\n🔍 调试信息: 检测到 {len(account_ids)} 个账户: {account_ids}')
        
        if account_ids:
            print('\n\033[36m可用账户:\033[0m')
            for account_id in account_ids:
                credentials = qwen_api.auth_manager.get_account_credentials(account_id)
                is_valid = credentials and qwen_api.auth_manager.is_token_valid(credentials)
                status = '✅ 有效' if is_valid else '❌ 无效/已过期'
                print(f"  {account_id}: {status}")
        else:
            # 检查是否存在默认账户
            default_credentials = await qwen_api.auth_manager.load_credentials()
            if default_credentials:
                is_valid = qwen_api.auth_manager.is_token_valid(default_credentials)
                status = '✅ 有效' if is_valid else '❌ 无效/已过期'
                print(f'\n\033[36m默认账户: {status}\033[0m')
            else:
                print('\n\033[36m未配置账户。请先进行认证。\033[0m')
    except Exception as error:
        print('\n\033[33m警告: 无法加载账户信息\033[0m')
    
    yield
    
    # 关闭时
    logger.info("Qwen OpenAI代理服务器关闭")


# 创建FastAPI应用
app = FastAPI(
    title="Qwen OpenAI代理",
    description="通过OpenAI兼容API公开Qwen模型的代理服务器",
    version="1.0.0",
    lifespan=lifespan
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QwenOpenAIProxy:
    """Qwen OpenAI代理类."""
    
    async def handle_chat_completion(self, request: ChatCompletionRequest, raw_request: Request) -> Union[JSONResponse, StreamingResponse]:
        """处理聊天完成请求."""
        try:
            # 计算请求中的token数量
            token_count = count_tokens(request.messages)
            
            # 在终端显示token数量
            print(f'\033[36m收到聊天完成请求，包含 {token_count} 个token\033[0m')
            
            # 检查是否请求流式且已启用
            is_streaming = request.stream and config.stream
            
            if is_streaming:
                # 处理流式响应
                return await self.handle_streaming_chat_completion(request, raw_request)
            else:
                # 处理常规响应
                # 如果客户端请求流式但已禁用，我们仍然使用常规完成
                return await self.handle_regular_chat_completion(request, raw_request)
                
        except Exception as error:
            # 记录API调用及错误
            request_data = await self._serialize_request(raw_request, request.model_dump())
            debug_filename = await debug_logger.log_api_call('/v1/chat/completions', request_data, None, error)
            
            # 以红色打印错误消息
            if debug_filename:
                print(f'\033[31m处理聊天完成请求时出错。调试日志保存到: {debug_filename}\033[0m')
            else:
                print('\033[31m处理聊天完成请求时出错。\033[0m')
            
            # 处理认证错误
            if 'Not authenticated' in str(error) or 'access token' in str(error):
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": {
                            "message": "未与Qwen认证。请先进行认证。",
                            "type": "authentication_error"
                        }
                    }
                )
            
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "message": str(error),
                        "type": "internal_server_error"
                    }
                }
            )
    
    async def handle_regular_chat_completion(self, request: ChatCompletionRequest, raw_request: Request) -> JSONResponse:
        """处理常规聊天完成."""
        try:
            # 通过我们集成的客户端调用Qwen API
            response = await qwen_api.chat_completions(request)
            
            # 记录API调用
            request_data = await self._serialize_request(raw_request, request.model_dump())
            debug_filename = await debug_logger.log_api_call('/v1/chat/completions', request_data, response)
            
            # 如果响应中有使用数据，显示token使用情况
            token_info = ''
            if response and 'usage' in response:
                usage = response['usage']
                prompt_tokens = usage.get('prompt_tokens', 0)
                completion_tokens = usage.get('completion_tokens', 0)
                total_tokens = usage.get('total_tokens', 0)
                token_info = f" (提示: {prompt_tokens}, 完成: {completion_tokens}, 总计: {total_tokens} tokens)"
            
            # 以绿色打印成功消息和调试文件信息
            if debug_filename:
                print(f'\033[32m聊天完成请求处理成功{token_info}。调试日志保存到: {debug_filename}\033[0m')
            else:
                print(f'\033[32m聊天完成请求处理成功{token_info}。\033[0m')
            
            return JSONResponse(content=response)
            
        except Exception as error:
            raise error  # 重新抛出以由主处理器处理
    
    async def handle_streaming_chat_completion(self, request: ChatCompletionRequest, raw_request: Request) -> StreamingResponse:
        """处理流式聊天完成."""
        try:
            # 记录API调用（没有响应数据，因为它是流式的）
            request_data = await self._serialize_request(raw_request, request.model_dump())
            debug_filename = await debug_logger.log_api_call('/v1/chat/completions', request_data, {"streaming": True})
            
            # 打印流式请求消息
            print(f'\033[32m流式聊天完成请求开始。调试日志保存到: {debug_filename}\033[0m')
            
            # 调用Qwen API流式方法
            stream_generator = qwen_api.stream_chat_completions(request)
            
            async def generate():
                try:
                    async for chunk in stream_generator:
                        yield chunk
                except Exception as error:
                    print(f'\033[31m流式聊天完成出错: {str(error)}\033[0m')
                    yield f'data: {{"error": {{"message": "{str(error)}", "type": "streaming_error"}}}}\n\n'
            
            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Access-Control-Allow-Origin": "*"
                }
            )
            
        except Exception as error:
            raise error  # 重新抛出以由主处理器处理
    
    async def handle_models(self, raw_request: Request) -> JSONResponse:
        """处理模型列表请求."""
        try:
            # 在终端显示请求
            print('\033[36m收到模型请求\033[0m')
            
            # 从Qwen获取模型
            models = await qwen_api.list_models()
            models_dict = models.model_dump()
            
            # 记录API调用
            request_data = await self._serialize_request(raw_request)
            debug_filename = await debug_logger.log_api_call('/v1/models', request_data, models_dict)
            
            # 以绿色打印成功消息和调试文件信息
            if debug_filename:
                print(f'\033[32m模型请求处理成功。调试日志保存到: {debug_filename}\033[0m')
            else:
                print('\033[32m模型请求处理成功。\033[0m')
            
            return JSONResponse(content=models_dict)
            
        except Exception as error:
            # 记录API调用及错误
            request_data = await self._serialize_request(raw_request)
            debug_filename = await debug_logger.log_api_call('/v1/models', request_data, None, error)
            
            # 以红色打印错误消息
            if debug_filename:
                print(f'\033[31m获取模型时出错。调试日志保存到: {debug_filename}\033[0m')
            else:
                print('\033[31m获取模型时出错。\033[0m')
            
            # 处理认证错误
            if 'Not authenticated' in str(error) or 'access token' in str(error):
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": {
                            "message": "未与Qwen认证。请先进行认证。",
                            "type": "authentication_error"
                        }
                    }
                )
            
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "message": str(error),
                        "type": "internal_server_error"
                    }
                }
            )
    
    async def handle_embeddings(self, request: EmbeddingRequest, raw_request: Request) -> JSONResponse:
        """处理嵌入向量请求."""
        try:
            # 计算请求中的token数量
            if isinstance(request.input, list):
                token_count = sum(count_tokens(text) for text in request.input)
            else:
                token_count = count_tokens(request.input)
            
            # 在终端显示token数量
            print(f'\033[36m收到嵌入向量请求，包含 {token_count} 个token\033[0m')
            
            # 调用Qwen嵌入向量API
            embeddings = await qwen_api.create_embeddings(request)
            
            # 记录API调用
            request_data = await self._serialize_request(raw_request, request.model_dump())
            debug_filename = await debug_logger.log_api_call('/v1/embeddings', request_data, embeddings)
            
            # 如果响应中有使用数据，显示token使用情况
            token_info = ''
            if embeddings and 'usage' in embeddings:
                usage = embeddings['usage']
                prompt_tokens = usage.get('prompt_tokens', 0)
                total_tokens = usage.get('total_tokens', 0)
                token_info = f" (提示: {prompt_tokens}, 总计: {total_tokens} tokens)"
            
            # 以绿色打印成功消息和调试文件信息
            if debug_filename:
                print(f'\033[32m嵌入向量请求处理成功{token_info}。调试日志保存到: {debug_filename}\033[0m')
            else:
                print(f'\033[32m嵌入向量请求处理成功{token_info}。\033[0m')
            
            return JSONResponse(content=embeddings)
            
        except Exception as error:
            # 记录API调用及错误
            request_data = await self._serialize_request(raw_request, request.model_dump())
            await debug_logger.log_api_call('/v1/embeddings', request_data, None, error)
            
            # 以红色打印错误消息
            print(f'\033[31m处理嵌入向量请求时出错: {str(error)}\033[0m')
            
            # 处理认证错误
            if 'Not authenticated' in str(error) or 'access token' in str(error):
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": {
                            "message": "未与Qwen认证。请先进行认证。",
                            "type": "authentication_error"
                        }
                    }
                )
            
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "message": str(error),
                        "type": "internal_server_error"
                    }
                }
            )
    
    async def handle_auth_initiate(self, raw_request: Request) -> JSONResponse:
        """处理认证启动请求."""
        try:
            # 启动设备流程
            device_flow = await auth_manager.initiate_device_flow()
            
            response = {
                "verification_uri": device_flow.verification_uri,
                "user_code": device_flow.user_code,
                "device_code": device_flow.device_code,
                "code_verifier": device_flow.code_verifier  # 应该安全存储用于轮询
            }
            
            # 记录API调用
            request_data = await self._serialize_request(raw_request)
            debug_filename = await debug_logger.log_api_call('/auth/initiate', request_data, response)
            
            # 以绿色打印成功消息和调试文件信息
            if debug_filename:
                print(f'\033[32m认证启动请求处理成功。调试日志保存到: {debug_filename}\033[0m')
            else:
                print('\033[32m认证启动请求处理成功。\033[0m')
            
            return JSONResponse(content=response)
            
        except Exception as error:
            # 记录API调用及错误
            request_data = await self._serialize_request(raw_request)
            await debug_logger.log_api_call('/auth/initiate', request_data, None, error)
            
            # 以红色打印错误消息
            print(f'\033[31m启动认证时出错: {str(error)}\033[0m')
            
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "message": str(error),
                        "type": "authentication_error"
                    }
                }
            )
    
    async def handle_auth_poll(self, poll_data: Dict[str, Any], raw_request: Request) -> JSONResponse:
        """处理认证轮询请求."""
        try:
            device_code = poll_data.get('device_code')
            code_verifier = poll_data.get('code_verifier')
            
            if not device_code or not code_verifier:
                error_response = {
                    "error": {
                        "message": "缺少device_code或code_verifier",
                        "type": "invalid_request"
                    }
                }
                
                # 记录API调用及错误
                request_data = await self._serialize_request(raw_request, poll_data)
                await debug_logger.log_api_call('/auth/poll', request_data, None, Exception('缺少device_code或code_verifier'))
                
                # 以红色打印错误消息
                print('\033[31m认证轮询错误: 缺少device_code或code_verifier\033[0m')
                
                return JSONResponse(status_code=400, content=error_response)
            
            # 轮询token
            credentials = await auth_manager.poll_for_token(device_code, code_verifier)
            
            response = {
                "access_token": credentials.access_token,
                "message": "认证成功"
            }
            
            # 记录API调用
            request_data = await self._serialize_request(raw_request, poll_data)
            debug_filename = await debug_logger.log_api_call('/auth/poll', request_data, response)
            
            # 以绿色打印成功消息和调试文件信息
            if debug_filename:
                print(f'\033[32m认证轮询请求处理成功。调试日志保存到: {debug_filename}\033[0m')
            else:
                print('\033[32m认证轮询请求处理成功。\033[0m')
            
            return JSONResponse(content=response)
            
        except Exception as error:
            # 记录API调用及错误
            request_data = await self._serialize_request(raw_request, poll_data)
            await debug_logger.log_api_call('/auth/poll', request_data, None, error)
            
            # 以红色打印错误消息
            print(f'\033[31m轮询token时出错: {str(error)}\033[0m')
            
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "message": str(error),
                        "type": "authentication_error"
                    }
                }
            )
    
    async def _serialize_request(self, raw_request: Request, body_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """序列化请求数据以用于日志记录."""
        try:
            if body_data is None:
                try:
                    body_data = await raw_request.json()
                except:
                    body_data = {}
            
            return {
                "method": raw_request.method,
                "url": str(raw_request.url),
                "headers": dict(raw_request.headers),
                "body": body_data
            }
        except:
            return {
                "method": raw_request.method,
                "url": str(raw_request.url),
                "headers": {},
                "body": body_data or {}
            }


# 初始化代理
proxy = QwenOpenAIProxy()


# 路由定义
@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest, raw_request: Request, token: str = Depends(verify_token)):
    """聊天完成端点."""
    return await proxy.handle_chat_completion(request, raw_request)


@app.get("/v1/models")
async def list_models(raw_request: Request, token: str = Depends(verify_token)):
    """模型列表端点."""
    return await proxy.handle_models(raw_request)


@app.post("/v1/embeddings")
async def create_embeddings(request: EmbeddingRequest, raw_request: Request, token: str = Depends(verify_token)):
    """嵌入向量端点."""
    return await proxy.handle_embeddings(request, raw_request)


@app.post("/auth/initiate")
async def auth_initiate(raw_request: Request, token: str = Depends(verify_token)):
    """认证启动端点."""
    return await proxy.handle_auth_initiate(raw_request)


@app.post("/auth/poll")
async def auth_poll(poll_data: dict, raw_request: Request, token: str = Depends(verify_token)):
    """认证轮询端点."""
    return await proxy.handle_auth_poll(poll_data, raw_request)


@app.get("/health")
async def health_check():
    """健康检查端点."""
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        reload=False,
        access_log=False
    )