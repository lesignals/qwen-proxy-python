#!/usr/bin/env python3
"""Qwen认证管理工具."""

import sys
import asyncio
import argparse
from typing import Optional

try:
    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False

from qwen.auth import QwenAuthManager


class QwenAuth:
    """Qwen认证工具类."""
    
    def __init__(self):
        """初始化认证工具."""
        self.auth_manager = QwenAuthManager()
    
    async def authenticate(self, account_id: Optional[str] = None):
        """执行认证流程."""
        try:
            print("启动Qwen认证...")
            
            # 启动设备授权流程
            device_flow = await self.auth_manager.initiate_device_flow()
            
            print(f"\n🔗 请访问以下链接进行认证:")
            print(f"{device_flow.verification_uri}")
            
            # 如果verification_uri已经包含完整参数，直接使用
            if 'user_code=' in device_flow.verification_uri:
                print("✅ 此链接已包含用户代码，直接点击即可")
            else:
                # 否则显示需要手动输入的信息
                print(f"\n📝 用户代码: {device_flow.user_code}")
                print("请在打开的页面中输入此代码")
            
            print(f"⏰ 代码有效期: {device_flow.expires_in // 60} 分钟")
            
            # 显示二维码（使用验证URL）
            if QRCODE_AVAILABLE:
                try:
                    qr = qrcode.QRCode(version=1, box_size=10, border=5)
                    qr.add_data(device_flow.verification_uri)
                    qr.make(fit=True)
                    print(f"\n📱 扫描二维码:")
                    qr.print_ascii()
                except Exception:
                    print("无法显示二维码")
            else:
                print("(未安装qrcode库，跳过二维码显示)")
            
            print("\n等待授权...")
            print("(按 Ctrl+C 取消)")
            
            # 轮询token
            credentials = await self.auth_manager.poll_for_token(
                device_flow.device_code,
                device_flow.code_verifier,
                account_id
            )
            
            if account_id:
                print(f"\n✅ 账户 '{account_id}' 认证成功!")
            else:
                print("\n✅ 认证成功!")
            
            print(f"访问token: {credentials.access_token[:20]}...")
            
        except KeyboardInterrupt:
            print("\n❌ 用户取消认证")
            sys.exit(1)
        except Exception as error:
            print(f"\n❌ 认证失败: {error}")
            sys.exit(1)
    
    async def list_accounts(self):
        """列出所有账户."""
        try:
            await self.auth_manager.load_all_accounts()
            account_ids = self.auth_manager.get_account_ids()
            
            if not account_ids:
                # 检查默认账户
                default_credentials = await self.auth_manager.load_credentials()
                if default_credentials:
                    is_valid = self.auth_manager.is_token_valid(default_credentials)
                    status = "✅ 有效" if is_valid else "❌ 无效/已过期"
                    print(f"默认账户: {status}")
                else:
                    print("❌ 未找到账户")
                return
            
            print("已配置的账户:")
            for account_id in account_ids:
                credentials = self.auth_manager.get_account_credentials(account_id)
                is_valid = credentials and self.auth_manager.is_token_valid(credentials)
                status = "✅ 有效" if is_valid else "❌ 无效/已过期"
                request_count = self.auth_manager.get_request_count(account_id)
                print(f"  {account_id}: {status} (今日请求: {request_count})")
                
        except Exception as error:
            print(f"❌ 列出账户失败: {error}")
            sys.exit(1)
    
    async def add_account(self, account_id: str):
        """添加新账户."""
        try:
            # 检查账户是否已存在
            await self.auth_manager.load_all_accounts()
            if self.auth_manager.get_account_credentials(account_id):
                print(f"❌ 账户 '{account_id}' 已存在")
                sys.exit(1)
            
            print(f"为账户 '{account_id}' 添加认证...")
            await self.authenticate(account_id)
            
        except Exception as error:
            print(f"❌ 添加账户失败: {error}")
            sys.exit(1)
    
    async def remove_account(self, account_id: str):
        """删除账户."""
        try:
            await self.auth_manager.load_all_accounts()
            
            # 检查账户是否存在
            if not self.auth_manager.get_account_credentials(account_id):
                print(f"❌ 账户 '{account_id}' 不存在")
                sys.exit(1)
            
            # 确认删除
            confirm = input(f"确定要删除账户 '{account_id}'? (y/N): ")
            if confirm.lower() not in ['y', 'yes']:
                print("❌ 操作已取消")
                return
            
            await self.auth_manager.remove_account(account_id)
            print(f"✅ 账户 '{account_id}' 已删除")
            
        except Exception as error:
            print(f"❌ 删除账户失败: {error}")
            sys.exit(1)
    
    async def show_counts(self):
        """显示请求计数."""
        try:
            await self.auth_manager.load_all_accounts()
            await self.auth_manager.load_request_counts()  # 确保加载请求计数
            account_ids = self.auth_manager.get_account_ids()
            
            print("账户请求计数 (今日):")
            total_requests = 0
            
            if account_ids:
                # 显示多账户
                for account_id in account_ids:
                    count = self.auth_manager.get_request_count(account_id)
                    total_requests += count
                    print(f"  {account_id}: {count} 次请求")
            else:
                # 显示单账户（默认账户）
                default_count = self.auth_manager.get_request_count("default")
                total_requests += default_count
                print(f"  default: {default_count} 次请求")
                
                # 检查是否有默认认证
                default_credentials = await self.auth_manager.load_credentials()
                if default_credentials:
                    is_valid = self.auth_manager.is_token_valid(default_credentials)
                    status = "✅ 有效" if is_valid else "❌ 无效/已过期"
                    print(f"  状态: {status}")
            
            print(f"\n总计: {total_requests} 次请求")
            print(f"重置日期: {self.auth_manager.last_reset_date} (UTC)")
            
        except Exception as error:
            print(f"❌ 显示计数失败: {error}")
            sys.exit(1)


async def main():
    """主函数."""
    parser = argparse.ArgumentParser(description="Qwen认证管理工具")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # 认证命令
    auth_parser = subparsers.add_parser("auth", help="进行认证")
    auth_parser.add_argument("account_id", nargs="?", help="账户ID（可选）")
    
    # 列表命令
    subparsers.add_parser("list", help="列出所有账户")
    
    # 添加命令
    add_parser = subparsers.add_parser("add", help="添加新账户")
    add_parser.add_argument("account_id", help="要添加的账户ID")
    
    # 删除命令
    remove_parser = subparsers.add_parser("remove", help="删除账户")
    remove_parser.add_argument("account_id", help="要删除的账户ID")
    
    # 计数命令
    subparsers.add_parser("counts", help="显示请求计数")
    
    args = parser.parse_args()
    
    # 如果没有命令，默认进行认证
    if not args.command:
        args.command = "auth"
    
    auth_tool = QwenAuth()
    
    try:
        if args.command == "auth":
            account_id = getattr(args, "account_id", None)
            await auth_tool.authenticate(account_id)
        elif args.command == "list":
            await auth_tool.list_accounts()
        elif args.command == "add":
            await auth_tool.add_account(args.account_id)
        elif args.command == "remove":
            await auth_tool.remove_account(args.account_id)
        elif args.command == "counts":
            await auth_tool.show_counts()
        else:
            print(f"❌ 未知命令: {args.command}")
            parser.print_help()
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n❌ 操作被用户取消")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())