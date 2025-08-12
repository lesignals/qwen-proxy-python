"""Token计数工具."""

from typing import List, Union

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

from models import Message


def count_tokens(messages: Union[List[Message], List[dict], str]) -> int:
    """计算消息的token数量."""
    if TIKTOKEN_AVAILABLE:
        try:
            # 使用tiktoken精确计算
            encoding = tiktoken.get_encoding("cl100k_base")
            
            if isinstance(messages, str):
                return len(encoding.encode(messages))
            
            total_tokens = 0
            for message in messages:
                if isinstance(message, Message):
                    text = message.content
                elif isinstance(message, dict):
                    text = message.get('content', '')
                else:
                    text = str(message)
                
                if text:
                    total_tokens += len(encoding.encode(text))
            
            return total_tokens
            
        except Exception:
            # tiktoken失败，回退到估算
            pass
    
    # 估算方法（当tiktoken不可用时）
    if isinstance(messages, str):
        return estimate_tokens(messages)
    
    total_chars = 0
    for message in messages:
        if isinstance(message, Message):
            total_chars += len(message.content)
        elif isinstance(message, dict):
            total_chars += len(message.get('content', ''))
        else:
            total_chars += len(str(message))
    
    return estimate_tokens_from_chars(total_chars)


def estimate_tokens(text: str) -> int:
    """估算文本的token数量."""
    # 简单的估算规则：
    # 英文: ~4字符 = 1 token
    # 中文: ~2字符 = 1 token
    # 混合: ~3字符 = 1 token
    
    if not text:
        return 0
    
    # 统计中文字符
    chinese_chars = sum(1 for char in text if '\u4e00' <= char <= '\u9fff')
    english_chars = len(text) - chinese_chars
    
    # 根据语言特性估算
    estimated_tokens = (chinese_chars // 2) + (english_chars // 4)
    
    # 至少返回1个token（如果有文本的话）
    return max(1, estimated_tokens) if text.strip() else 0


def estimate_tokens_from_chars(total_chars: int) -> int:
    """从字符总数估算token数量."""
    # 平均估算：3字符 = 1 token
    return max(1, total_chars // 3) if total_chars > 0 else 0