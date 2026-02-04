"""
检索智能体单元测试
"""
import sys
import os
import json

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_serialize_module():
    """测试模块序列化功能"""
    from agents.retrieval_agent import RetrievalAgent
    
    print("=" * 60)
    print("测试 1: 模块序列化")
    print("=" * 60)
    
    agent = RetrievalAgent()
    
    # 读取一个示例模块
    test_file = "./schemas/logic/比较判断.json"
    
    if not os.path.exists(test_file):
        print(f"❌ 测试文件不存在: {test_file}")
        return False
    
    with open(test_file, 'r', encoding='utf-8') as f:
        module_json = json.load(f)
    
    # 序列化
    text = agent._serialize_module_to_text(module_json)
    
    print("\n序列化结果:")
    print("-" * 60)
    print(text)
    print("-" * 60)
    
    # 验证
    assert "# 模块名称:" in text
    assert "功能描述" in text
    assert "关键词" in text
    
    print("\n✅ 测试通过！")
    return True


def test_extract_metadata():
    """测试元数据提取功能"""
    from agents.retrieval_agent import RetrievalAgent
    
    print("\n" + "=" * 60)
    print("测试 2: 元数据提取")
    print("=" * 60)
    
    agent = RetrievalAgent()
    
    # 读取示例模块
    test_file = "./schemas/variable/变量.json"
    
    if not os.path.exists(test_file):
        print(f"❌ 测试文件不存在: {test_file}")
        return False
    
    with open(test_file, 'r', encoding='utf-8') as f:
        module_json = json.load(f)
    
    # 提取元数据
    metadata = agent._extract_metadata(module_json)
    
    print("\n提取的元数据:")
    print("-" * 60)
    for key, value in metadata.items():
        if key != 'json_schema':  # 太长，不显示
            print(f"{key}: {value}")
    print("-" * 60)
    
    # 验证
    assert 'module_type' in metadata
    assert 'category_l1' in metadata
    assert 'category_l2' in metadata
    
    print("\n✅ 测试通过！")
    return True


def test_generate_example():
    """测试示例代码生成"""
    from agents.retrieval_agent import RetrievalAgent
    
    print("\n" + "=" * 60)
    print("测试 3: 示例代码生成")
    print("=" * 60)
    
    agent = RetrievalAgent()
    
    # 读取示例模块
    test_file = "./schemas/math/加.json"
    
    if not os.path.exists(test_file):
        print(f"⚠️  测试文件不存在: {test_file}，跳过此测试")
        return True
    
    with open(test_file, 'r', encoding='utf-8') as f:
        module_json = json.load(f)
    
    # 生成示例
    example = agent._generate_example_code(module_json)
    
    print("\n生成的示例代码:")
    print("-" * 60)
    print(example)
    print("-" * 60)
    
    # 验证
    assert "node = {" in example
    assert "'type':" in example
    
    print("\n✅ 测试通过！")
    return True


def test_knowledge_base_loading():
    """测试知识库加载"""
    from agents.retrieval_agent import RetrievalAgent
    
    print("\n" + "=" * 60)
    print("测试 4: 知识库加载")
    print("=" * 60)
    
    agent = RetrievalAgent()
    
    # 加载知识库
    print("\n开始加载知识库...")
    agent.load_knowledge_base("./schemas")
    
    # 验证
    count = agent.collection.count()
    print(f"\n向量数据库包含 {count} 条记录")
    
    assert count > 0, "知识库应该包含至少一条记录"
    
    print("\n✅ 测试通过！")
    return True


def test_retrieval():
    """测试检索功能"""
    from agents.retrieval_agent import RetrievalAgent
    
    print("\n" + "=" * 60)
    print("测试 5: 检索功能")
    print("=" * 60)
    
    agent = RetrievalAgent()
    
    # 确保知识库已加载
    if agent.collection.count() == 0:
        print("\n⚠️  知识库为空，先加载...")
        agent.load_knowledge_base("./schemas")
    
    # 测试查询
    test_queries = [
        "比较两个数值的大小",
        "读取传感器数据",
        "计算夏季主机负荷，公式为：4.18×(冷冻回水温度-冷冻供水温度)×冷冻水流量÷3.6",
    ]
    
    for query in test_queries:
        print(f"\n查询: {query}")
        result = agent.retrieve(query, top_k=8)
        
        print(f"找到 {len(result['relevant_nodes'])} 个相关模块:")
        for node in result['relevant_nodes']:
            print(f"  - {node['name']} (分数: {node['similarity_score']:.3f})")
        
        assert len(result['relevant_nodes']) > 0, f"应该能找到与 '{query}' 相关的模块"
    
    print("\n✅ 测试通过！")
    return True


def run_all_tests():
    """运行所有测试"""
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 15 + "检索智能体单元测试" + " " * 15 + "║")
    print("╚" + "═" * 58 + "╝")
    print()
    
    # tests = [
    #     ("模块序列化", test_serialize_module),
    #     ("元数据提取", test_extract_metadata),
    #     ("示例代码生成", test_generate_example),
    #     ("知识库加载", test_knowledge_base_loading),
    #     ("检索功能", test_retrieval)
    # ]
    tests = [
        ("检索功能（增强模式）", test_retrieval)
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
                print(f"❌ {name} 测试失败")
        except Exception as e:
            failed += 1
            print(f"\n❌ {name} 测试出错: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print(f"测试完成: {passed} 通过, {failed} 失败")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
