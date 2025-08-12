"""调试日志记录工具."""

import os
import json
import structlog
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from config import config


class DebugLogger:
    """调试日志记录器."""
    
    def __init__(self):
        """初始化日志记录器."""
        self.logger = structlog.get_logger()
        self.log_dir = Path.home() / '.qwen' / 'debug_logs'
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
    async def log_api_call(
        self,
        endpoint: str,
        request_data: Dict[str, Any],
        response_data: Optional[Dict[str, Any]] = None,
        error: Optional[Exception] = None
    ) -> Optional[str]:
        """记录API调用日志."""
        if not config.debug_log:
            return None
            
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
            log_filename = f"{endpoint.replace('/', '_')}_{timestamp}.json"
            log_filepath = self.log_dir / log_filename
            
            log_data = {
                'timestamp': datetime.now().isoformat(),
                'endpoint': endpoint,
                'request': request_data,
            }
            
            if response_data:
                log_data['response'] = response_data
                log_data['status'] = 'success'
            
            if error:
                log_data['error'] = {
                    'message': str(error),
                    'type': type(error).__name__
                }
                log_data['status'] = 'error'
            
            # 写入日志文件
            with open(log_filepath, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)
            
            # 清理旧的日志文件
            await self._cleanup_old_logs()
            
            return str(log_filepath)
            
        except Exception as e:
            self.logger.error(f"Failed to write debug log: {e}")
            return None
    
    async def _cleanup_old_logs(self):
        """清理旧的日志文件."""
        try:
            log_files = list(self.log_dir.glob('*.json'))
            
            if len(log_files) > config.log_file_limit:
                # 按修改时间排序，删除最旧的文件
                log_files.sort(key=lambda f: f.stat().st_mtime)
                files_to_remove = log_files[:-config.log_file_limit]
                
                for file_path in files_to_remove:
                    try:
                        file_path.unlink()
                    except Exception as e:
                        self.logger.warning(f"Failed to remove log file {file_path}: {e}")
                        
        except Exception as e:
            self.logger.error(f"Failed to cleanup old logs: {e}")