"""Qwen API客户端."""

import json
import asyncio
from typing import Optional, Dict, Any, AsyncGenerator
from datetime import datetime

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from models import (
    ChatCompletionRequest, 
    EmbeddingRequest,
    ChatCompletionResponse,
    EmbeddingResponse,
    ModelsResponse,
    ModelData,
    QwenCredentials
)
from qwen.auth import QwenAuthManager
from config import config


# 已知的Qwen模型
QWEN_MODELS = [
    ModelData(id='qwen3-coder-plus', object='model', created=1754686206, owned_by='qwen'),
    ModelData(id='qwen3-coder-turbo', object='model', created=1754686206, owned_by='qwen'),
    ModelData(id='qwen3-plus', object='model', created=1754686206, owned_by='qwen'),
    ModelData(id='qwen3-turbo', object='model', created=1754686206, owned_by='qwen')
]


def is_auth_error(error: Exception) -> bool:
    """检查错误是否与认证/授权相关."""
    if not error:
        return False
    
    error_message = str(error).lower()
    
    # 检查HTTP状态码
    if hasattr(error, 'response') and hasattr(error.response, 'status_code'):
        status_code = error.response.status_code
        if status_code in [400, 401, 403, 504]:
            return True
    
    # 检查错误消息
    auth_keywords = [
        'unauthorized', 'forbidden', 'invalid api key', 'invalid access token',
        'token expired', 'authentication', 'access denied', '504', 'gateway timeout'
    ]
    
    return any(keyword in error_message for keyword in auth_keywords)


def is_quota_exceeded_error(error: Exception) -> bool:
    """检查错误是否与配额限制相关."""
    if not error:
        return False
    
    error_message = str(error).lower()
    
    # 检查HTTP状态码
    if hasattr(error, 'response') and hasattr(error.response, 'status_code'):
        status_code = error.response.status_code
        if status_code == 429:
            return True
    
    # 检查错误消息
    quota_keywords = [
        'insufficient_quota', 'free allocated quota exceeded', 'quota exceeded'
    ]
    
    return any(keyword in error_message for keyword in quota_keywords)


class QwenAPI:
    """Qwen API客户端."""
    
    def __init__(self):
        """初始化API客户端."""
        self.auth_manager = QwenAuthManager()
    
    async def get_api_endpoint(self, credentials: Optional[QwenCredentials]) -> str:
        """获取API端点."""
        if credentials and credentials.resource_url:
            endpoint = credentials.resource_url
            # 确保它有scheme
            if not endpoint.startswith('http'):
                endpoint = f"https://{endpoint}"
            # 确保它有/v1后缀
            if not endpoint.endswith('/v1'):
                if endpoint.endswith('/'):
                    endpoint += 'v1'
                else:
                    endpoint += '/v1'
            return endpoint
        else:
            # 使用默认端点
            return config.default_api_base_url
    
    async def chat_completions(self, request: ChatCompletionRequest) -> Dict[str, Any]:
        """聊天完成API调用."""
        # 加载所有账户以支持多账户
        await self.auth_manager.load_all_accounts()
        account_ids = self.auth_manager.get_account_ids()
        
        # 如果没有额外账户，使用默认行为
        if not account_ids:
            return await self.chat_completions_single_account(request)
        
        # 从第一个账户开始（粘性选择）
        current_account_index = 0
        last_error = None
        max_retries = len(account_ids)
        
        for i in range(max_retries):
            try:
                # 获取当前账户（粘性直到配额错误）
                account_id = account_ids[current_account_index]
                credentials = self.auth_manager.get_account_credentials(account_id)
                
                if not credentials:
                    # 如果当前账户无效，移动到下一个账户
                    current_account_index = (current_account_index + 1) % len(account_ids)
                    continue
                
                # 显示正在使用的账户
                request_count = self.auth_manager.get_request_count(account_id) + 1
                print(f'\033[36m使用账户 {account_id} (今日第 #{request_count} 次请求)\033[0m')
                
                # 获取此账户的有效访问token
                access_token = await self.auth_manager.get_valid_access_token(account_id)
                
                # 获取API端点
                api_endpoint = await self.get_api_endpoint(credentials)
                
                # 进行API调用
                url = f"{api_endpoint}/chat/completions"
                payload = {
                    'model': request.model or config.default_model,
                    'messages': [msg.model_dump() for msg in request.messages],
                    'temperature': request.temperature,
                    'max_tokens': request.max_tokens,
                    'top_p': request.top_p,
                    'tools': request.tools,
                    'tool_choice': request.tool_choice
                }
                
                headers = {
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {access_token}',
                    'User-Agent': 'QwenOpenAIProxy/1.0.0 (linux; x64)'
                }
                
                # 增加此账户的请求计数
                await self.auth_manager.increment_request_count(account_id)
                updated_count = self.auth_manager.get_request_count(account_id)
                print(f'\033[36m使用账户 {account_id} (今日第 #{updated_count} 次请求)\033[0m')
                
                async with httpx.AsyncClient(timeout=config.api_timeout) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    return response.json()
                    
            except Exception as error:
                last_error = error
                
                # 检查是否为配额超出错误
                if is_quota_exceeded_error(error):
                    print(f'\033[33m账户 {account_id} 配额已超出 (第 #{self.auth_manager.get_request_count(account_id)} 次请求)，轮换到下一个账户...\033[0m')
                    # 移动到下一个账户用于下次请求
                    current_account_index = (current_account_index + 1) % len(account_ids)
                    # 预览下一个账户以显示我们将轮换到哪个
                    next_account_id = account_ids[current_account_index]
                    print(f'\033[33m将尝试下一个账户 {next_account_id}\033[0m')
                    # 继续到下一个账户
                    continue
                
                # 检查是否为可能受益于重试的认证错误
                if is_auth_error(error):
                    print(f'\033[33m检测到认证错误 ({getattr(error.response, "status_code", "N/A") if hasattr(error, "response") else "N/A"})，尝试刷新token并重试...\033[0m')
                    try:
                        account_info = await self.auth_manager.get_next_account()
                        if account_info:
                            account_id = account_info["accountId"]
                            credentials = account_info["credentials"]
                            # 强制刷新token并重试一次
                            await self.auth_manager.perform_token_refresh(credentials, account_id)
                            new_access_token = await self.auth_manager.get_valid_access_token(account_id)
                            
                            # 使用新token重试请求
                            print('\033[36m使用刷新后的token重试请求...\033[0m')
                            retry_headers = {
                                'Content-Type': 'application/json',
                                'Authorization': f'Bearer {new_access_token}',
                                'User-Agent': 'QwenOpenAIProxy/1.0.0 (linux; x64)'
                            }
                            
                            # 增加此账户的请求计数
                            await self.auth_manager.increment_request_count(account_id)
                            
                            async with httpx.AsyncClient(timeout=config.api_timeout) as client:
                                retry_response = await client.post(url, json=payload, headers=retry_headers)
                                retry_response.raise_for_status()
                                print('\033[32m刷新token后请求成功\033[0m')
                                return retry_response.json()
                    except Exception as retry_error:
                        print('\033[31m即使刷新token后请求仍然失败\033[0m')
                        # 如果重试失败，继续到下一个账户
                        continue
                
                # 对于其他错误，重新抛出
                if hasattr(error, 'response'):
                    # 请求已发出，服务器返回状态码
                    error_data = error.response.json() if hasattr(error.response, 'json') else str(error.response.text)
                    raise HTTPException(
                        status_code=error.response.status_code,
                        detail=f"Qwen API错误: {error.response.status_code} {error_data}"
                    )
                else:
                    # 请求发出但未收到响应，或设置请求时发生错误
                    raise HTTPException(status_code=500, detail=f"Qwen API请求失败: {str(error)}")
        
        # 如果到达这里，所有账户都失败了
        raise HTTPException(status_code=500, detail=f"所有账户都失败了。最后错误: {str(last_error)}")
    
    async def chat_completions_single_account(self, request: ChatCompletionRequest) -> Dict[str, Any]:
        """单账户聊天完成API调用."""
        # 获取有效的访问token（需要时自动刷新）
        access_token = await self.auth_manager.get_valid_access_token()
        credentials = await self.auth_manager.load_credentials()
        api_endpoint = await self.get_api_endpoint(credentials)
        
        # 进行API调用
        url = f"{api_endpoint}/chat/completions"
        payload = {
            'model': request.model or config.default_model,
            'messages': [msg.model_dump() for msg in request.messages],
            'temperature': request.temperature,
            'max_tokens': request.max_tokens,
            'top_p': request.top_p,
            'tools': request.tools,
            'tool_choice': request.tool_choice
        }
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}',
            'User-Agent': 'QwenOpenAIProxy/1.0.0 (linux; x64)'
        }
        
        try:
            async with httpx.AsyncClient(timeout=config.api_timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                return response.json()
                
        except Exception as error:
            # 检查是否为可能受益于重试的认证错误
            if is_auth_error(error):
                print(f'\033[33m检测到认证错误 ({getattr(error.response, "status_code", "N/A") if hasattr(error, "response") else "N/A"})，尝试刷新token并重试...\033[0m')
                try:
                    # 强制刷新token并重试一次
                    await self.auth_manager.perform_token_refresh(credentials)
                    new_access_token = await self.auth_manager.get_valid_access_token()
                    
                    # 使用新token重试请求
                    print('\033[36m使用刷新后的token重试请求...\033[0m')
                    retry_headers = {
                        'Content-Type': 'application/json',
                        'Authorization': f'Bearer {new_access_token}',
                        'User-Agent': 'QwenOpenAIProxy/1.0.0 (linux; x64)'
                    }
                    
                    async with httpx.AsyncClient(timeout=config.api_timeout) as client:
                        retry_response = await client.post(url, json=payload, headers=retry_headers)
                        retry_response.raise_for_status()
                        print('\033[32m刷新token后请求成功\033[0m')
                        return retry_response.json()
                        
                except Exception as retry_error:
                    print('\033[31m即使刷新token后请求仍然失败\033[0m')
                    # 如果重试失败，抛出带有额外上下文的原始错误
                    if hasattr(error, 'response'):
                        error_data = error.response.json() if hasattr(error.response, 'json') else str(error.response.text)
                        raise HTTPException(
                            status_code=error.response.status_code,
                            detail=f"Qwen API错误（刷新token尝试后）: {error.response.status_code} {error_data}"
                        )
            
            if hasattr(error, 'response'):
                # 请求已发出，服务器返回状态码
                error_data = error.response.json() if hasattr(error.response, 'json') else str(error.response.text)
                raise HTTPException(
                    status_code=error.response.status_code,
                    detail=f"Qwen API错误: {error.response.status_code} {error_data}"
                )
            else:
                # 请求发出但未收到响应，或设置请求时发生错误
                raise HTTPException(status_code=500, detail=f"Qwen API请求失败: {str(error)}")
    
    async def list_models(self) -> ModelsResponse:
        """列出模型."""
        print("返回模拟模型列表")
        
        # 返回Qwen模型的模拟列表，因为Qwen API没有此端点
        return ModelsResponse(
            object="list",
            data=QWEN_MODELS
        )
    
    async def create_embeddings(self, request: EmbeddingRequest) -> Dict[str, Any]:
        """创建嵌入向量."""
        # 加载所有账户以支持多账户
        await self.auth_manager.load_all_accounts()
        account_ids = self.auth_manager.get_account_ids()
        
        # 如果没有额外账户，使用默认行为
        if not account_ids:
            # 获取有效的访问token（需要时自动刷新）
            access_token = await self.auth_manager.get_valid_access_token()
            credentials = await self.auth_manager.load_credentials()
            api_endpoint = await self.get_api_endpoint(credentials)
            
            # 进行API调用
            url = f"{api_endpoint}/embeddings"
            payload = {
                'model': request.model or 'text-embedding-v1',
                'input': request.input
            }
            
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {access_token}',
                'User-Agent': 'QwenOpenAIProxy/1.0.0 (linux; x64)'
            }
            
            try:
                async with httpx.AsyncClient(timeout=config.api_timeout) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    return response.json()
                    
            except Exception as error:
                # 检查是否为可能受益于重试的认证错误
                if is_auth_error(error):
                    print(f'\033[33m检测到认证错误 ({getattr(error.response, "status_code", "N/A") if hasattr(error, "response") else "N/A"})，尝试刷新token并重试...\033[0m')
                    try:
                        # 强制刷新token并重试一次
                        await self.auth_manager.perform_token_refresh(credentials)
                        new_access_token = await self.auth_manager.get_valid_access_token()
                        
                        # 使用新token重试请求
                        print('\033[36m使用刷新后的token重试请求...\033[0m')
                        retry_headers = {
                            'Content-Type': 'application/json',
                            'Authorization': f'Bearer {new_access_token}',
                            'User-Agent': 'QwenOpenAIProxy/1.0.0 (linux; x64)'
                        }
                        
                        async with httpx.AsyncClient(timeout=config.api_timeout) as client:
                            retry_response = await client.post(url, json=payload, headers=retry_headers)
                            retry_response.raise_for_status()
                            print('\033[32m刷新token后请求成功\033[0m')
                            return retry_response.json()
                            
                    except Exception as retry_error:
                        print('\033[31m即使刷新token后请求仍然失败\033[0m')
                        # 如果重试失败，抛出带有额外上下文的原始错误
                        if hasattr(error, 'response'):
                            error_data = error.response.json() if hasattr(error.response, 'json') else str(error.response.text)
                            raise HTTPException(
                                status_code=error.response.status_code,
                                detail=f"Qwen API错误（刷新token尝试后）: {error.response.status_code} {error_data}"
                            )
                
                if hasattr(error, 'response'):
                    # 请求已发出，服务器返回状态码
                    error_data = error.response.json() if hasattr(error.response, 'json') else str(error.response.text)
                    raise HTTPException(
                        status_code=error.response.status_code,
                        detail=f"Qwen API错误: {error.response.status_code} {error_data}"
                    )
                else:
                    # 请求发出但未收到响应，或设置请求时发生错误
                    raise HTTPException(status_code=500, detail=f"Qwen API请求失败: {str(error)}")
        else:
            # 多账户逻辑与chat_completions类似
            # 从第一个账户开始（粘性选择）
            current_account_index = 0
            last_error = None
            max_retries = len(account_ids)
            
            for i in range(max_retries):
                try:
                    # 获取当前账户（粘性直到配额错误）
                    account_id = account_ids[current_account_index]
                    credentials = self.auth_manager.get_account_credentials(account_id)
                    
                    if not credentials:
                        # 如果当前账户无效，移动到下一个账户
                        current_account_index = (current_account_index + 1) % len(account_ids)
                        continue
                    
                    # 显示正在使用的账户
                    request_count = self.auth_manager.get_request_count(account_id) + 1
                    print(f'\033[36m使用账户 {account_id} (今日第 #{request_count} 次请求)\033[0m')
                    
                    # 获取此账户的有效访问token
                    access_token = await self.auth_manager.get_valid_access_token(account_id)
                    
                    # 获取API端点
                    api_endpoint = await self.get_api_endpoint(credentials)
                    
                    # 进行API调用
                    url = f"{api_endpoint}/embeddings"
                    payload = {
                        'model': request.model or 'text-embedding-v1',
                        'input': request.input
                    }
                    
                    headers = {
                        'Content-Type': 'application/json',
                        'Authorization': f'Bearer {access_token}',
                        'User-Agent': 'QwenOpenAIProxy/1.0.0 (linux; x64)'
                    }
                    
                    # 增加此账户的请求计数
                    await self.auth_manager.increment_request_count(account_id)
                    
                    async with httpx.AsyncClient(timeout=config.api_timeout) as client:
                        response = await client.post(url, json=payload, headers=headers)
                        response.raise_for_status()
                        return response.json()
                        
                except Exception as error:
                    last_error = error
                    
                    # 检查是否为配额超出错误
                    if is_quota_exceeded_error(error):
                        print(f'\033[33m账户 {account_id} 配额已超出 (第 #{self.auth_manager.get_request_count(account_id)} 次请求)，轮换到下一个账户...\033[0m')
                        # 移动到下一个账户用于下次请求
                        current_account_index = (current_account_index + 1) % len(account_ids)
                        # 预览下一个账户以显示我们将轮换到哪个
                        next_account_id = account_ids[current_account_index]
                        print(f'\033[33m将尝试下一个账户 {next_account_id}\033[0m')
                        # 继续到下一个账户
                        continue
                    
                    # 其他错误处理与chat_completions类似
                    if hasattr(error, 'response'):
                        error_data = error.response.json() if hasattr(error.response, 'json') else str(error.response.text)
                        raise HTTPException(
                            status_code=error.response.status_code,
                            detail=f"Qwen API错误: {error.response.status_code} {error_data}"
                        )
                    else:
                        raise HTTPException(status_code=500, detail=f"Qwen API请求失败: {str(error)}")
            
            # 如果到达这里，所有账户都失败了
            raise HTTPException(status_code=500, detail=f"所有账户都失败了。最后错误: {str(last_error)}")
    
    async def stream_chat_completions(self, request: ChatCompletionRequest) -> AsyncGenerator[str, None]:
        """流式聊天完成."""
        # 加载所有账户以支持多账户
        await self.auth_manager.load_all_accounts()
        account_ids = self.auth_manager.get_account_ids()
        
        # 如果没有额外账户，使用默认行为
        if not account_ids:
            # 获取有效的访问token（需要时自动刷新）
            access_token = await self.auth_manager.get_valid_access_token()
            credentials = await self.auth_manager.load_credentials()
            api_endpoint = await self.get_api_endpoint(credentials)
            
            # 进行流式API调用
            url = f"{api_endpoint}/chat/completions"
            payload = {
                'model': request.model or config.default_model,
                'messages': [msg.model_dump() for msg in request.messages],
                'temperature': request.temperature,
                'max_tokens': request.max_tokens,
                'top_p': request.top_p,
                'tools': request.tools,
                'tool_choice': request.tool_choice,
                'stream': True,  # 启用流式
                'stream_options': {'include_usage': True}  # 在最终块中包含使用数据
            }
            
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {access_token}',
                'User-Agent': 'QwenOpenAIProxy/1.0.0 (linux; x64)',
                'Accept': 'text/event-stream'
            }
            
            try:
                async with httpx.AsyncClient(timeout=config.api_timeout) as client:
                    async with client.stream('POST', url, json=payload, headers=headers) as response:
                        response.raise_for_status()
                        
                        async for chunk in response.aiter_text():
                            if chunk:
                                yield chunk
                                
            except Exception as error:
                # 检查是否为可能受益于重试的认证错误
                if is_auth_error(error):
                    print(f'\033[33m检测到认证错误 ({getattr(error.response, "status_code", "N/A") if hasattr(error, "response") else "N/A"})，尝试刷新token并重试...\033[0m')
                    try:
                        # 强制刷新token并重试一次
                        await self.auth_manager.perform_token_refresh(credentials)
                        new_access_token = await self.auth_manager.get_valid_access_token()
                        
                        # 使用新token重试请求
                        print('\033[36m使用刷新后的token重试流式请求...\033[0m')
                        retry_headers = {
                            'Content-Type': 'application/json',
                            'Authorization': f'Bearer {new_access_token}',
                            'User-Agent': 'QwenOpenAIProxy/1.0.0 (linux; x64)',
                            'Accept': 'text/event-stream'
                        }
                        
                        async with httpx.AsyncClient(timeout=config.api_timeout) as client:
                            async with client.stream('POST', url, json=payload, headers=retry_headers) as retry_response:
                                retry_response.raise_for_status()
                                print('\033[32m刷新token后流式请求成功\033[0m')
                                
                                async for chunk in retry_response.aiter_text():
                                    if chunk:
                                        yield chunk
                                        
                    except Exception as retry_error:
                        print('\033[31m即使刷新token后流式请求仍然失败\033[0m')
                        # 如果重试失败，抛出带有额外上下文的原始错误
                        raise HTTPException(
                            status_code=500,
                            detail=f"Qwen API流式错误（刷新token尝试后）: {str(error)}"
                        )
                
                if hasattr(error, 'response'):
                    # 请求已发出，服务器返回状态码
                    error_data = error.response.json() if hasattr(error.response, 'json') else str(error.response.text)
                    raise HTTPException(
                        status_code=error.response.status_code,
                        detail=f"Qwen API错误: {error.response.status_code} {error_data}"
                    )
                else:
                    # 请求发出但未收到响应，或设置请求时发生错误
                    raise HTTPException(status_code=500, detail=f"Qwen API请求失败: {str(error)}")
        else:
            # 多账户流式处理逻辑
            # 从第一个账户开始（粘性选择）
            current_account_index = 0
            last_error = None
            max_retries = len(account_ids)
            
            for i in range(max_retries):
                try:
                    # 获取当前账户（粘性直到配额错误）
                    account_id = account_ids[current_account_index]
                    credentials = self.auth_manager.get_account_credentials(account_id)
                    
                    if not credentials:
                        # 如果当前账户无效，移动到下一个账户
                        current_account_index = (current_account_index + 1) % len(account_ids)
                        continue
                    
                    # 显示正在使用的账户
                    request_count = self.auth_manager.get_request_count(account_id) + 1
                    print(f'\033[36m使用账户 {account_id} (今日第 #{request_count} 次请求)\033[0m')
                    
                    # 获取此账户的有效访问token
                    access_token = await self.auth_manager.get_valid_access_token(account_id)
                    
                    # 获取API端点
                    api_endpoint = await self.get_api_endpoint(credentials)
                    
                    # 进行流式API调用
                    url = f"{api_endpoint}/chat/completions"
                    payload = {
                        'model': request.model or config.default_model,
                        'messages': [msg.model_dump() for msg in request.messages],
                        'temperature': request.temperature,
                        'max_tokens': request.max_tokens,
                        'top_p': request.top_p,
                        'tools': request.tools,
                        'tool_choice': request.tool_choice,
                        'stream': True,  # 启用流式
                        'stream_options': {'include_usage': True}  # 在最终块中包含使用数据
                    }
                    
                    headers = {
                        'Content-Type': 'application/json',
                        'Authorization': f'Bearer {access_token}',
                        'User-Agent': 'QwenOpenAIProxy/1.0.0 (linux; x64)',
                        'Accept': 'text/event-stream'
                    }
                    
                    # 增加此账户的请求计数
                    await self.auth_manager.increment_request_count(account_id)
                    
                    async with httpx.AsyncClient(timeout=config.api_timeout) as client:
                        async with client.stream('POST', url, json=payload, headers=headers) as response:
                            response.raise_for_status()
                            
                            async for chunk in response.aiter_text():
                                if chunk:
                                    yield chunk
                    
                    return  # 成功完成，退出循环
                    
                except Exception as error:
                    last_error = error
                    
                    # 检查是否为配额超出错误
                    if is_quota_exceeded_error(error):
                        print(f'\033[33m账户 {account_id} 配额已超出 (第 #{self.auth_manager.get_request_count(account_id)} 次请求)，轮换到下一个账户...\033[0m')
                        # 移动到下一个账户用于下次请求
                        current_account_index = (current_account_index + 1) % len(account_ids)
                        # 预览下一个账户以显示我们将轮换到哪个
                        next_account_id = account_ids[current_account_index]
                        print(f'\033[33m将尝试下一个账户 {next_account_id}\033[0m')
                        # 继续到下一个账户
                        continue
                    
                    # 其他错误处理
                    if hasattr(error, 'response'):
                        error_data = error.response.json() if hasattr(error.response, 'json') else str(error.response.text)
                        raise HTTPException(
                            status_code=error.response.status_code,
                            detail=f"Qwen API错误: {error.response.status_code} {error_data}"
                        )
                    else:
                        raise HTTPException(status_code=500, detail=f"Qwen API请求失败: {str(error)}")
            
            # 如果到达这里，所有账户都失败了
            raise HTTPException(status_code=500, detail=f"所有账户都失败了。最后错误: {str(last_error)}")