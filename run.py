#!/usr/bin/env python3
"""运行脚本."""

import sys
import argparse
import asyncio
import uvicorn
from config import config


def main():
    """主函数."""
    parser = argparse.ArgumentParser(description="Qwen OpenAI代理服务器")
    parser.add_argument("--host", default=config.host, help=f"绑定地址 (默认: {config.host})")
    parser.add_argument("--port", type=int, default=config.port, help=f"监听端口 (默认: {config.port})")
    parser.add_argument("--reload", action="store_true", help="启用自动重载 (开发模式)")
    parser.add_argument("--log-level", default="info", choices=["critical", "error", "warning", "info", "debug"], help="日志级别")
    
    args = parser.parse_args()
    
    try:
        uvicorn.run(
            "main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level=args.log_level,
            access_log=False
        )
    except KeyboardInterrupt:
        print("\n服务器已停止")
        sys.exit(0)
    except Exception as error:
        print(f"启动服务器时出错: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()