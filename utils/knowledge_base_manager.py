"""
知识库管理器
负责知识库的创建、更新、删除等维护操作
"""
from typing import Dict, List, Any, Optional
import json
import os
from pathlib import Path
import config
from utils.console_utils import safe_print as print
from agents.retrieval_agent import RetrievalAgent


class KnowledgeBaseManager:
    """知识库管理器"""
    
    def __init__(self, retrieval_agent: Optional[RetrievalAgent] = None):
        """
        初始化知识库管理器
        
        Args:
            retrieval_agent: 检索智能体实例，如果不提供则创建新实例
        """
        self.agent = retrieval_agent or RetrievalAgent()
    
    def update_single_module(self, json_file_path: str) -> bool:
        """
        更新单个模块的向量表示
        
        Args:
            json_file_path: 模块 JSON 文件的路径
            
        Returns:
            是否更新成功
        """
        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                module_json = json.load(f)
            
            # 生成语义文本块
            doc_text = self.agent._serialize_module_to_text(module_json)
            
            # 提取元数据
            metadata = self.agent._extract_metadata(module_json)
            
            # 生成唯一 ID
            module_type = module_json.get('module_type', '')
            category = module_json.get('category', '').replace('/', '_')
            doc_id = f"{category}_{module_type}"
            
            # 更新到向量数据库
            self.agent.collection.upsert(
                documents=[doc_text],
                metadatas=[metadata],
                ids=[doc_id]
            )
            
            if config.DEBUG:
                print(f"✅ 已更新模块: {module_json.get('name')} ({module_type})")
            
            return True
        
        except Exception as e:
            if config.DEBUG:
                print(f"❌ 更新失败 {json_file_path}: {e}")
            return False
    
    def update_multiple_modules(self, json_file_paths: List[str]) -> Dict[str, int]:
        """
        批量更新多个模块的向量表示
        
        Args:
            json_file_paths: 模块 JSON 文件路径列表
            
        Returns:
            更新统计信息 {'success': 成功数, 'failed': 失败数}
        """
        documents = []
        metadatas = []
        ids = []
        success_count = 0
        failed_count = 0
        
        for json_file in json_file_paths:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    module_json = json.load(f)
                
                # 生成语义文本块
                doc_text = self.agent._serialize_module_to_text(module_json)
                
                # 提取元数据
                metadata = self.agent._extract_metadata(module_json)
                
                # 生成唯一 ID
                module_type = module_json.get('module_type', '')
                category = module_json.get('category', '').replace('/', '_')
                doc_id = f"{category}_{module_type}"
                
                documents.append(doc_text)
                metadatas.append(metadata)
                ids.append(doc_id)
                
                if config.DEBUG:
                    print(f"   准备更新: {module_json.get('name')} ({module_type})")
                
                success_count += 1
            
            except Exception as e:
                if config.DEBUG:
                    print(f"   ❌ 读取失败 {json_file}: {e}")
                failed_count += 1
        
        # 批量更新
        if documents:
            try:
                self.agent.collection.upsert(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids
                )
                
                if config.DEBUG:
                    print(f"\n✅ 批量更新完成: 成功 {success_count} 个，失败 {failed_count} 个")
            
            except Exception as e:
                if config.DEBUG:
                    print(f"\n❌ 批量更新失败: {e}")
                return {'success': 0, 'failed': len(json_file_paths)}
        
        return {'success': success_count, 'failed': failed_count}
    
    def delete_module(self, module_type: str, category: str) -> bool:
        """
        删除指定模块的向量表示
        
        Args:
            module_type: 模块类型
            category: 模块类别（如 "逻辑模块/比较判断"）
            
        Returns:
            是否删除成功
        """
        try:
            doc_id = f"{category.replace('/', '_')}_{module_type}"
            self.agent.collection.delete(ids=[doc_id])
            
            if config.DEBUG:
                print(f"✅ 已删除模块: {module_type} (ID: {doc_id})")
            
            return True
        
        except Exception as e:
            if config.DEBUG:
                print(f"❌ 删除失败: {e}")
            return False
    
    def rebuild_knowledge_base(self, schemas_dir: str = "./schemas"):
        """
        重建整个知识库（清空后重新加载）
        
        Args:
            schemas_dir: JSON Schema 文件所在目录
        """
        try:
            # 删除旧集合
            self.agent.client.delete_collection(name="kong_modules_v1")
            
            if config.DEBUG:
                print("🗑️  已删除旧知识库")
            
            # 创建新集合
            self.agent.collection = self.agent.client.create_collection(
                name="kong_modules_v1",
                embedding_function=self.agent.embedding_function,
                metadata={"description": "KONG CUBE 模块知识库"}
            )
            
            if config.DEBUG:
                print("📦 已创建新知识库集合")
            
            # 重新加载
            self.agent.load_knowledge_base(schemas_dir)
        
        except Exception as e:
            if config.DEBUG:
                print(f"❌ 重建知识库失败: {e}")
    
    def get_module_info(self, module_type: str, category: str) -> Optional[Dict[str, Any]]:
        """
        获取指定模块的信息
        
        Args:
            module_type: 模块类型
            category: 模块类别
            
        Returns:
            模块信息字典，如果不存在返回 None
        """
        try:
            doc_id = f"{category.replace('/', '_')}_{module_type}"
            result = self.agent.collection.get(ids=[doc_id])
            
            if result and result['metadatas'] and len(result['metadatas']) > 0:
                metadata = result['metadatas'][0]
                module_schema = json.loads(metadata.get('json_schema', '{}'))
                return module_schema
            
            return None
        
        except Exception as e:
            if config.DEBUG:
                print(f"❌ 获取模块信息失败: {e}")
            return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取知识库统计信息
        
        Returns:
            统计信息字典
        """
        try:
            total_count = self.agent.collection.count()
            
            # 获取所有模块的元数据进行分类统计
            if total_count > 0:
                all_data = self.agent.collection.get()
                metadatas = all_data.get('metadatas', [])
                
                # 按类别统计
                category_stats = {}
                for metadata in metadatas:
                    category = metadata.get('category_l1', '未分类')
                    category_stats[category] = category_stats.get(category, 0) + 1
                
                return {
                    'total_modules': total_count,
                    'category_distribution': category_stats
                }
            
            return {
                'total_modules': 0,
                'category_distribution': {}
            }
        
        except Exception as e:
            if config.DEBUG:
                print(f"❌ 获取统计信息失败: {e}")
            return {
                'total_modules': 0,
                'category_distribution': {},
                'error': str(e)
            }
