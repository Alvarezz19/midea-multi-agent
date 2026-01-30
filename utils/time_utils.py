"""
时间工具函数
"""
from datetime import datetime


def get_timestamp_str(format_type: str = "filename") -> str:
    """
    获取格式化的时间戳字符串
    
    Args:
        format_type: 格式类型
            - "filename": 适用于文件名的格式 (MMDD_HHMMSS)
            - "full": 完整格式 (YYYY-MM-DD HH:MM:SS)
            - "date": 日期格式 (YYYY-MM-DD)
            
    Returns:
        格式化的时间字符串
    """
    now = datetime.now()
    
    if format_type == "filename":
        # 格式: 0126_224650 (月日_时分秒)
        return now.strftime("%m%d_%H%M%S")
    elif format_type == "full":
        # 格式: 2026-01-26 22:46:50
        return now.strftime("%Y-%m-%d %H:%M:%S")
    elif format_type == "date":
        # 格式: 2026-01-26
        return now.strftime("%Y-%m-%d")
    else:
        return now.strftime("%m%d_%H%M%S")


def generate_output_filename(prefix: str = "模块", ext: str = "json") -> str:
    """
    生成带时间戳的输出文件名
    
    Args:
        prefix: 文件名前缀
        ext: 文件扩展名（不带点）
        
    Returns:
        格式化的文件名，例如: "模块0126_224650.json"
    """
    timestamp = get_timestamp_str("filename")
    return f"{prefix}{timestamp}.{ext}"
