"""Qwen认证管理器."""

import os
import json
import hashlib
import base64
import secrets
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from datetime import datetime

import httpx
import qrcode
from models import QwenCredentials, DeviceFlowResponse, TokenResponse
from config import config


# 文件系统配置
QWEN_DIR = '.qwen'
QWEN_CREDENTIAL_FILENAME = 'oauth_creds.json'
QWEN_MULTI_ACCOUNT_PREFIX = 'oauth_creds_'
QWEN_MULTI_ACCOUNT_SUFFIX = '.json'

# OAuth配置
TOKEN_REFRESH_BUFFER_MS = 30 * 1000  # 30秒


def generate_code_verifier() -> str:
    """生成PKCE代码验证器."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip('=')


def generate_code_challenge(code_verifier: str) -> str:
    """从代码验证器生成代码挑战."""
    digest = hashlib.sha256(code_verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip('=')


def generate_pkce_pair() -> Tuple[str, str]:
    """生成PKCE代码验证器和挑战对."""
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    return code_verifier, code_challenge


class QwenAuthManager:
    """Qwen认证管理器."""
    
    def __init__(self):
        """初始化认证管理器."""
        self.qwen_dir = Path.home() / QWEN_DIR
        self.qwen_dir.mkdir(exist_ok=True)
        
        self.credentials_path = self.qwen_dir / QWEN_CREDENTIAL_FILENAME
        self.credentials: Optional[QwenCredentials] = None
        self.refresh_lock = asyncio.Lock()
        self.accounts: Dict[str, QwenCredentials] = {}
        self.current_account_index = 0
        self.request_counts: Dict[str, int] = {}
        self.last_reset_date = datetime.now().strftime('%Y-%m-%d')
        self.request_count_file = self.qwen_dir / 'request_counts.json'
        
        # 加载请求计数将在第一次调用时完成
    
    async def load_credentials(self) -> Optional[QwenCredentials]:
        """加载默认凭据."""
        if self.credentials:
            return self.credentials
        
        try:
            if self.credentials_path.exists():
                data = json.loads(self.credentials_path.read_text(encoding='utf-8'))
                self.credentials = QwenCredentials(**data)
                return self.credentials
        except Exception:
            pass
        
        return None
    
    async def load_all_accounts(self) -> Dict[str, QwenCredentials]:
        """加载所有多账户凭据."""
        try:
            self.accounts.clear()
            
            # 读取目录中的所有凭据文件
            for file_path in self.qwen_dir.glob(f"{QWEN_MULTI_ACCOUNT_PREFIX}*{QWEN_MULTI_ACCOUNT_SUFFIX}"):
                try:
                    data = json.loads(file_path.read_text(encoding='utf-8'))
                    credentials = QwenCredentials(**data)
                    
                    # 从文件名提取账户ID
                    filename = file_path.name
                    account_id = filename[len(QWEN_MULTI_ACCOUNT_PREFIX):-len(QWEN_MULTI_ACCOUNT_SUFFIX)]
                    
                    self.accounts[account_id] = credentials
                except Exception as e:
                    print(f"警告: 无法加载账户文件 {file_path}: {e}")
            
            return self.accounts
        except Exception as e:
            print(f"警告: 无法加载多账户凭据: {e}")
            return self.accounts
    
    async def save_credentials(self, credentials: QwenCredentials, account_id: Optional[str] = None):
        """保存凭据."""
        try:
            cred_data = credentials.model_dump()
            
            if account_id:
                # 保存到特定账户文件
                account_filename = f"{QWEN_MULTI_ACCOUNT_PREFIX}{account_id}{QWEN_MULTI_ACCOUNT_SUFFIX}"
                account_path = self.qwen_dir / account_filename
                account_path.write_text(json.dumps(cred_data, indent=2, ensure_ascii=False), encoding='utf-8')
                
                # 更新账户映射
                self.accounts[account_id] = credentials
            else:
                # 保存到默认凭据文件
                self.credentials_path.write_text(json.dumps(cred_data, indent=2, ensure_ascii=False), encoding='utf-8')
                self.credentials = credentials
        except Exception as e:
            print(f"错误: 保存凭据失败: {e}")
    
    def is_token_valid(self, credentials: QwenCredentials) -> bool:
        """检查token是否有效."""
        if not credentials or not credentials.expiry_date:
            return False
        
        current_time = int(datetime.now().timestamp() * 1000)
        return current_time < credentials.expiry_date - TOKEN_REFRESH_BUFFER_MS
    
    def get_account_ids(self) -> list[str]:
        """获取所有账户ID列表."""
        return list(self.accounts.keys())
    
    def get_account_credentials(self, account_id: str) -> Optional[QwenCredentials]:
        """获取特定账户的凭据."""
        return self.accounts.get(account_id)
    
    async def add_account(self, credentials: QwenCredentials, account_id: str):
        """添加新账户."""
        await self.save_credentials(credentials, account_id)
    
    async def remove_account(self, account_id: str):
        """删除账户."""
        try:
            account_filename = f"{QWEN_MULTI_ACCOUNT_PREFIX}{account_id}{QWEN_MULTI_ACCOUNT_SUFFIX}"
            account_path = self.qwen_dir / account_filename
            
            # 删除文件
            if account_path.exists():
                account_path.unlink()
            
            # 从账户映射中删除
            if account_id in self.accounts:
                del self.accounts[account_id]
            
            print(f"账户 {account_id} 已成功删除")
        except Exception as e:
            print(f"错误: 删除账户 {account_id} 失败: {e}")
            raise
    
    async def load_request_counts(self):
        """从磁盘加载请求计数."""
        try:
            if self.request_count_file.exists():
                data = json.loads(self.request_count_file.read_text(encoding='utf-8'))
                
                # 恢复上次重置日期
                if 'lastResetDate' in data:
                    self.last_reset_date = data['lastResetDate']
                
                # 恢复请求计数
                if 'requests' in data:
                    self.request_counts = data['requests']
                
                # 如果跨入新的UTC日，重置计数
                self.reset_request_counts_if_needed()
        except Exception:
            # 文件不存在或无效，从空计数开始
            self.reset_request_counts_if_needed()
    
    async def save_request_counts(self):
        """将请求计数保存到磁盘."""
        try:
            data = {
                'lastResetDate': self.last_reset_date,
                'requests': self.request_counts
            }
            self.request_count_file.write_text(json.dumps(data, indent=2), encoding='utf-8')
        except Exception as e:
            print(f"警告: 保存请求计数失败: {e}")
    
    def reset_request_counts_if_needed(self):
        """如果跨入新的UTC日，重置请求计数."""
        today = datetime.now().strftime('%Y-%m-%d')
        if today != self.last_reset_date:
            self.request_counts.clear()
            self.last_reset_date = today
            print("新UTC日的请求计数已重置")
            asyncio.create_task(self.save_request_counts())
    
    async def increment_request_count(self, account_id: str):
        """增加账户的请求计数."""
        self.reset_request_counts_if_needed()
        current_count = self.request_counts.get(account_id, 0)
        self.request_counts[account_id] = current_count + 1
        await self.save_request_counts()
    
    def get_request_count(self, account_id: str) -> int:
        """获取账户的请求计数."""
        self.reset_request_counts_if_needed()
        return self.request_counts.get(account_id, 0)
    
    async def refresh_access_token(self, credentials: QwenCredentials) -> QwenCredentials:
        """刷新访问token."""
        print('\033[33m正在刷新Qwen访问token...\033[0m')
        
        if not credentials or not credentials.refresh_token:
            raise Exception("无刷新token可用。请使用Qwen CLI重新认证。")
        
        body_data = {
            'grant_type': 'refresh_token',
            'refresh_token': credentials.refresh_token,
            'client_id': config.qwen.client_id,
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    config.qwen.token_endpoint,
                    data=body_data,
                    headers={
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'Accept': 'application/json'
                    }
                )
                
                if response.status_code != 200:
                    error_data = response.json()
                    raise Exception(f"Token刷新失败: {error_data.get('error')} - {error_data.get('error_description')}")
                
                token_data = response.json()
                
                new_credentials = QwenCredentials(
                    access_token=token_data['access_token'],
                    token_type=token_data.get('token_type', 'Bearer'),
                    refresh_token=token_data.get('refresh_token', credentials.refresh_token),
                    resource_url=token_data.get('resource_url', credentials.resource_url),
                    expiry_date=int(datetime.now().timestamp() * 1000) + token_data['expires_in'] * 1000
                )
                
                print('\033[32mQwen访问token刷新成功\033[0m')
                return new_credentials
                
        except Exception as e:
            print('\033[31m刷新Qwen访问token失败\033[0m')
            raise Exception("刷新访问token失败。请使用Qwen CLI重新认证。")
    
    async def get_valid_access_token(self, account_id: Optional[str] = None) -> str:
        """获取有效的访问token."""
        async with self.refresh_lock:
            try:
                credentials = None
                
                if account_id:
                    # 获取特定账户的凭据
                    credentials = self.get_account_credentials(account_id)
                    if not credentials:
                        # 如果未加载，加载所有账户
                        await self.load_all_accounts()
                        credentials = self.get_account_credentials(account_id)
                else:
                    # 使用默认凭据
                    credentials = await self.load_credentials()
                
                if not credentials:
                    if account_id:
                        raise Exception(f"未找到账户 {account_id} 的凭据。请先认证此账户。")
                    else:
                        raise Exception("未找到凭据。请先使用Qwen CLI认证。")
                
                # 检查token是否有效
                if self.is_token_valid(credentials):
                    message = f"使用账户 {account_id} 的有效Qwen访问token" if account_id else "使用有效的Qwen访问token"
                    print(f'\033[32m{message}\033[0m')
                    return credentials.access_token
                else:
                    message = f"账户 {account_id} 的Qwen访问token已过期或即将过期，正在刷新..." if account_id else "Qwen访问token已过期或即将过期，正在刷新..."
                    print(f'\033[33m{message}\033[0m')
                
                # Token需要刷新
                new_credentials = await self.refresh_access_token(credentials)
                
                # 保存到适当的账户
                await self.save_credentials(new_credentials, account_id)
                
                return new_credentials.access_token
                
            except Exception as e:
                raise Exception(str(e))
    
    async def perform_token_refresh(self, credentials: QwenCredentials, account_id: Optional[str] = None) -> QwenCredentials:
        """执行token刷新."""
        try:
            new_credentials = await self.refresh_access_token(credentials)
            
            # 保存到适当的账户
            await self.save_credentials(new_credentials, account_id)
            
            return new_credentials
        except Exception as e:
            raise Exception(str(e))
    
    async def get_next_account(self) -> Optional[Dict[str, Any]]:
        """获取下一个可用账户进行轮询."""
        # 如果未加载账户，先加载
        if not self.accounts:
            await self.load_all_accounts()
        
        account_ids = self.get_account_ids()
        
        if not account_ids:
            return None
        
        # 使用轮询选择
        account_id = account_ids[self.current_account_index]
        credentials = self.get_account_credentials(account_id)
        
        # 更新下次调用的索引
        self.current_account_index = (self.current_account_index + 1) % len(account_ids)
        
        return {"accountId": account_id, "credentials": credentials}
    
    def is_account_valid(self, account_id: str) -> bool:
        """检查账户是否有有效凭据."""
        credentials = self.get_account_credentials(account_id)
        return credentials and self.is_token_valid(credentials)
    
    async def initiate_device_flow(self) -> DeviceFlowResponse:
        """启动设备授权流程."""
        # 生成PKCE代码验证器和挑战
        code_verifier, code_challenge = generate_pkce_pair()
        
        body_data = {
            'client_id': config.qwen.client_id,
            'scope': config.qwen.scope,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    config.qwen.device_code_endpoint,
                    data=body_data,
                    headers={
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'Accept': 'application/json'
                    }
                )
                
                if response.status_code != 200:
                    error_text = response.text
                    raise Exception(f"设备授权失败: {response.status_code} {response.reason_phrase}. 响应: {error_text}")
                
                result = response.json()
                
                # 检查响应是否表示成功
                if 'device_code' not in result:
                    error = result.get('error', '未知错误')
                    error_description = result.get('error_description', '无详细信息')
                    raise Exception(f"设备授权失败: {error} - {error_description}")
                
                # 将代码验证器添加到结果中，以便稍后用于轮询
                # 如果有完整的验证URI，使用它
                verification_uri = result.get('verification_uri_complete', result['verification_uri'])
                
                return DeviceFlowResponse(
                    device_code=result['device_code'],
                    user_code=result['user_code'],
                    verification_uri=verification_uri,
                    expires_in=result['expires_in'],
                    interval=result.get('interval', 5),
                    code_verifier=code_verifier
                )
                
        except Exception as e:
            print(f"设备授权流程失败: {e}")
            raise
    
    async def poll_for_token(
        self, 
        device_code: str, 
        code_verifier: str, 
        account_id: Optional[str] = None
    ) -> QwenCredentials:
        """轮询token."""
        poll_interval = 5  # 5秒
        max_attempts = 60  # 最多5分钟
        
        for attempt in range(max_attempts):
            body_data = {
                'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
                'client_id': config.qwen.client_id,
                'device_code': device_code,
                'code_verifier': code_verifier,
                'client': 'qwen-code',  # 添加client参数，根据API响应推断
            }
            
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        config.qwen.token_endpoint,
                        data=body_data,
                        headers={
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'Accept': 'application/json'
                        }
                    )
                    
                    if response.status_code != 200:
                        # 解析响应为JSON以检查OAuth RFC 8628标准错误
                        try:
                            error_data = response.json()
                            error_type = error_data.get('error', 'unknown_error')
                            error_desc = error_data.get('error_description', '无详细信息')
                            
                            # 根据OAuth RFC 8628处理标准轮询响应
                            if response.status_code == 400 and error_type == 'authorization_pending':
                                # 用户尚未批准授权请求。继续轮询。
                                print(f"轮询尝试 {attempt + 1}/{max_attempts}... (等待用户授权)")
                                await asyncio.sleep(poll_interval)
                                continue
                            
                            if response.status_code == 400 and error_type == 'slow_down':
                                # 客户端轮询过于频繁。增加轮询间隔。
                                poll_interval = min(poll_interval * 1.5, 10)  # 增加50%，最大10秒
                                print(f"服务器要求放慢速度，将轮询间隔增加到 {poll_interval:.1f}秒")
                                await asyncio.sleep(poll_interval)
                                continue
                            
                            if response.status_code == 400 and error_type == 'expired_token':
                                raise Exception("❌ 设备代码已过期。请重新启动认证过程。")
                            
                            if response.status_code == 400 and error_type == 'access_denied':
                                raise Exception("❌ 用户拒绝授权。请重新启动认证过程。")
                            
                            # 特殊处理无效用户代码的情况
                            if response.status_code == 400 and ('invalid' in error_type.lower() or 'invalid' in error_desc.lower()):
                                if 'user_code' in error_desc.lower() or 'code' in error_desc.lower():
                                    raise Exception(f"❌ 用户代码无效或已失效: {error_desc}\n请重新启动认证过程获取新的代码。")
                            
                            # 对于其他错误，抛出详细的错误信息
                            raise Exception(f"设备token轮询失败: {error_type} - {error_desc}")
                            
                        except json.JSONDecodeError:
                            # 如果JSON解析失败，回退到文本响应
                            error_text = response.text
                            raise Exception(f"设备token轮询失败: {response.status_code} {response.reason_phrase}. 响应: {error_text}")
                    
                    token_data = response.json()
                    
                    # 转换为QwenCredentials格式并保存
                    credentials = QwenCredentials(
                        access_token=token_data['access_token'],
                        refresh_token=token_data.get('refresh_token'),
                        token_type=token_data.get('token_type', 'Bearer'),
                        resource_url=token_data.get('resource_url') or token_data.get('endpoint'),
                        expiry_date=int(datetime.now().timestamp() * 1000) + token_data['expires_in'] * 1000 if token_data.get('expires_in') else None
                    )
                    
                    await self.save_credentials(credentials, account_id)
                    
                    return credentials
                    
            except Exception as e:
                # 处理特定错误情况
                error_message = str(e)
                
                # 如果我们得到应该停止轮询的特定OAuth错误，抛出它
                if ('expired_token' in error_message or 
                    'access_denied' in error_message or 
                    '设备授权失败' in error_message):
                    raise
                
                # 对于其他错误，继续轮询
                print(f"轮询尝试 {attempt + 1}/{max_attempts} 失败: {error_message}")
                await asyncio.sleep(poll_interval)
        
        raise Exception("认证超时。请重新启动认证过程。")