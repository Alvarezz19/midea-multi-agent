"""
自动同步schemas目录到向量数据库
监控schemas目录的变化，自动更新向量数据库
"""
import sys
import os
import time
from pathlib import Path
from typing import Set

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.knowledge_base_manager import KnowledgeBaseManager
import config


class SchemaWatcher:
    """文件监控器"""
    
    def __init__(self, schemas_dir: str = "./schemas"):
        self.schemas_dir = Path(schemas_dir)
        self.manager = KnowledgeBaseManager()
        self.file_timestamps = {}
        self._scan_files()
    
    def _scan_files(self):
        """扫描所有JSON文件并记录时间戳"""
        for json_file in self.schemas_dir.rglob("*.json"):
            if json_file.name != '扩展描述文件.json':
                self.file_timestamps[str(json_file)] = json_file.stat().st_mtime
    
    def check_changes(self) -> Set[str]:
        """
        检查文件变化
        
        Returns:
            变化的文件路径集合
        """
        changed_files = set()
        current_files = {}
        
        # 扫描当前文件
        for json_file in self.schemas_dir.rglob("*.json"):
            if json_file.name != '扩展描述文件.json':
                current_mtime = json_file.stat().st_mtime
                file_path = str(json_file)
                current_files[file_path] = current_mtime
                
                # 检查是否是新文件或修改过的文件
                if file_path not in self.file_timestamps:
                    print(f"📄 发现新文件: {json_file.name}")
                    changed_files.add(file_path)
                elif current_mtime > self.file_timestamps[file_path]:
                    print(f"📝 文件已修改: {json_file.name}")
                    changed_files.add(file_path)
        
        # 检查删除的文件
        deleted_files = set(self.file_timestamps.keys()) - set(current_files.keys())
        for deleted_file in deleted_files:
            print(f"🗑️  文件已删除: {Path(deleted_file).name}")
            # TODO: 实现删除逻辑（需要从文件路径推断module_type和category）
        
        # 更新时间戳记录
        self.file_timestamps = current_files
        
        return changed_files
    
    def sync_changes(self, changed_files: Set[str]):
        """
        同步变化到向量数据库
        
        Args:
            changed_files: 变化的文件路径集合
        """
        if not changed_files:
            return
        
        print(f"\n🔄 开始同步 {len(changed_files)} 个文件...")
        result = self.manager.update_multiple_modules(list(changed_files))
        print(f"✅ 同步完成: 成功 {result['success']} 个，失败 {result['failed']} 个\n")
    
    def watch(self, interval: int = 5):
        """
        持续监控文件变化
        
        Args:
            interval: 检查间隔（秒）
        """
        print("=" * 60)
        print("Schema文件自动同步工具")
        print(f"监控目录: {self.schemas_dir.absolute()}")
        print(f"检查间隔: {interval}秒")
        print("按 Ctrl+C 停止监控")
        print("=" * 60)
        print()
        
        try:
            while True:
                changed_files = self.check_changes()
                if changed_files:
                    self.sync_changes(changed_files)
                
                time.sleep(interval)
        
        except KeyboardInterrupt:
            print("\n\n👋 停止监控")


def one_time_sync(schemas_dir: str = "./schemas"):
    """
    一次性同步所有文件（用于脚本方式）
    
    Args:
        schemas_dir: schemas目录路径
    """
    print("=" * 60)
    print("Schema文件同步工具（一次性同步）")
    print("=" * 60)
    print()
    
    manager = KnowledgeBaseManager()
    
    # 查找所有JSON文件
    schemas_path = Path(schemas_dir)
    json_files = []
    for json_file in schemas_path.rglob("*.json"):
        if json_file.name != '扩展描述文件.json':
            json_files.append(str(json_file))
    
    if json_files:
        print(f"找到 {len(json_files)} 个模块文件")
        result = manager.update_multiple_modules(json_files)
        print(f"\n✅ 同步完成: 成功 {result['success']} 个，失败 {result['failed']} 个")
    else:
        print("❌ 未找到任何模块文件")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Schema文件自动同步工具')
    parser.add_argument('--mode', choices=['watch', 'sync'], default='watch',
                        help='运行模式: watch=持续监控, sync=一次性同步')
    parser.add_argument('--dir', default='./schemas',
                        help='schemas目录路径')
    parser.add_argument('--interval', type=int, default=5,
                        help='监控模式下的检查间隔（秒）')
    
    args = parser.parse_args()
    
    if args.mode == 'watch':
        watcher = SchemaWatcher(args.dir)
        watcher.watch(args.interval)
    else:
        one_time_sync(args.dir)
