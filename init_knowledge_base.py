"""
初始化向量数据库脚本
用于首次加载或重建知识库
"""
import sys
import os

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.retrieval_agent import RetrievalAgent
import config


def main():
    """主函数"""
    print("=" * 60)
    print("KONG CUBE 知识库初始化工具")
    print("=" * 60)
    
    # 创建检索智能体
    retrieval_agent = RetrievalAgent()
    
    # 加载知识库
    schemas_dir = "./schemas"
    
    if not os.path.exists(schemas_dir):
        print(f"❌ 错误: 找不到 schemas 目录: {schemas_dir}")
        return
    
    print(f"\n开始加载知识库...")
    print(f"数据源: {schemas_dir}")
    print(f"向量数据库: {config.CHROMA_PERSIST_DIR}")
    print()
    
    retrieval_agent.load_knowledge_base(schemas_dir)
    
    print("\n" + "=" * 60)
    print("知识库初始化完成！")
    print("=" * 60)
    
    # 测试检索
    print("\n进行简单测试...\n")
    
    test_queries = [
        "我需要比较两个温度值",
        "读取传感器数据",
        "定时器功能"
    ]
    
    for query in test_queries:
        print(f"测试查询: {query}")
        result = retrieval_agent.retrieve(query, top_k=3)
        
        if result['relevant_nodes']:
            print(f"  找到 {len(result['relevant_nodes'])} 个相关模块:")
            for node in result['relevant_nodes'][:3]:
                print(f"    - {node['name']} ({node['module_type']}) - 分数: {node['similarity_score']:.3f}")
        else:
            print("  未找到相关模块")
        print()


if __name__ == "__main__":
    main()
