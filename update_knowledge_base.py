"""
知识库更新工具
用于更新、删除或重建向量数据库中的模块
"""
import sys
import os

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.knowledge_base_manager import KnowledgeBaseManager
import config


def main():
    """主函数"""
    print("=" * 60)
    print("KONG CUBE 知识库更新工具")
    print("=" * 60)
    
    # 创建知识库管理器
    manager = KnowledgeBaseManager()
    
    print("\n请选择操作：")
    print("1. 更新单个模块")
    print("2. 批量更新多个模块")
    print("3. 删除指定模块")
    print("4. 重建整个知识库")
    print("5. 查看模块信息")
    print("6. 重新加载所有模块（增量更新）")
    print("7. 查看知识库统计")
    print("0. 退出")
    
    choice = input("\n请输入选项 (0-7): ").strip()
    
    if choice == "1":
        # 更新单个模块
        file_path = input("请输入模块JSON文件路径（相对或绝对路径）: ").strip()
        if os.path.exists(file_path):
            success = manager.update_single_module(file_path)
            if success:
                print("✅ 模块更新成功！")
            else:
                print("❌ 模块更新失败！")
        else:
            print(f"❌ 文件不存在: {file_path}")
    
    elif choice == "2":
        # 批量更新多个模块
        print("\n请输入要更新的模块JSON文件路径（每行一个，输入空行结束）：")
        file_paths = []
        while True:
            path = input().strip()
            if not path:
                break
            if os.path.exists(path):
                file_paths.append(path)
            else:
                print(f"⚠️  文件不存在，已跳过: {path}")
        
        if file_paths:
            result = manager.update_multiple_modules(file_paths)
            print(f"\n✅ 批量更新完成: 成功 {result['success']} 个，失败 {result['failed']} 个")
        else:
            print("❌ 没有有效的文件路径")
    
    elif choice == "3":
        # 删除模块
        module_type = input("请输入模块类型（如 'compare'）: ").strip()
        category = input("请输入模块类别（如 '逻辑模块/比较判断'）: ").strip()
        
        confirm = input(f"确认删除模块 {module_type} ({category})? (y/n): ").strip().lower()
        if confirm == 'y':
            success = manager.delete_module(module_type, category)
            if success:
                print("✅ 模块删除成功！")
            else:
                print("❌ 模块删除失败！")
        else:
            print("已取消删除操作")
    
    elif choice == "4":
        # 重建知识库
        confirm = input("⚠️  此操作将删除所有现有数据并重建知识库，确认继续？(y/n): ").strip().lower()
        if confirm == 'y':
            schemas_dir = input("请输入schemas目录路径（留空使用默认 './schemas'）: ").strip()
            if not schemas_dir:
                schemas_dir = "./schemas"
            
            manager.rebuild_knowledge_base(schemas_dir)
            print("✅ 知识库重建完成！")
        else:
            print("已取消重建操作")
    
    elif choice == "5":
        # 查看模块信息
        module_type = input("请输入模块类型（如 'compare'）: ").strip()
        category = input("请输入模块类别（如 '逻辑模块/比较判断'）: ").strip()
        
        info = manager.get_module_info(module_type, category)
        if info:
            print("\n" + "=" * 60)
            print(f"模块名称: {info.get('name')}")
            print(f"模块类型: {info.get('module_type')}")
            print(f"类别: {info.get('category')}")
            print(f"描述: {info.get('description')}")
            print(f"关键词: {', '.join(info.get('keywords', []))}")
            print("=" * 60)
        else:
            print("❌ 未找到该模块")
    
    elif choice == "6":
        # 重新加载所有模块（增量更新）
        schemas_dir = input("请输入schemas目录路径（留空使用默认 './schemas'）: ").strip()
        if not schemas_dir:
            schemas_dir = "./schemas"
        
        print("\n开始增量更新知识库...")
        manager.agent.load_knowledge_base(schemas_dir)
        print("✅ 增量更新完成！")
    
    elif choice == "7":
        # 查看知识库统计
        stats = manager.get_statistics()
        print("\n" + "=" * 60)
        print(f"知识库总模块数: {stats['total_modules']}")
        print("\n各类别分布:")
        for category, count in stats.get('category_distribution', {}).items():
            print(f"  - {category}: {count} 个")
        print("=" * 60)
    
    elif choice == "0":
        print("再见！")
        return
    
    else:
        print("❌ 无效的选项")


if __name__ == "__main__":
    main()
