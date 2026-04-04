# Phase 2 retrieval bundle tests.

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if 'agents.retrieval_agent' not in sys.modules:
    retrieval_stub = types.ModuleType('agents.retrieval_agent')

    class RetrievalAgent:
        pass

    retrieval_stub.RetrievalAgent = RetrievalAgent
    sys.modules['agents.retrieval_agent'] = retrieval_stub

import workflow
import workflow_trace
from utils.retrieval_bundle_utils import (
    build_allowed_module_types,
    build_compilable_doc_map,
    build_legacy_retrieval_context,
    get_atomic_modules,
    get_subflow_templates,
    is_retrieval_bundle,
    load_structured_payload,
)


def make_bundle():
    return {
        'atomic_modules': [
            {
                'module_type': 'constInput',
                'name': 'Constant Input',
                'category': 'logic/basic',
                'parameters_schema': {'fixedValue': {'type': 'number'}},
                'ports_definition': {'inputs': [], 'outputs': [{'label': 'out'}]},
                'template_json': {'type': 'constInput', 'inputs': 0, 'outputs': 1},
            }
        ],
        'subflow_templates': [
            {
                'module_type': 'fan_template',
                'template_id': 'fan_template',
                'definition_id': 'fan_template',
                'template_role': 'fan_control',
                'name': 'Fan Template',
                'category': 'ahu/subflow_templates/fan_control',
                'parameters_schema': {},
                'ports_definition': {'inputs': [], 'outputs': []},
                'template_json': {
                    'type': 'subflow',
                    'id': 'random-subflow-id',
                    'name': 'Fan Template',
                    'in': [],
                    'out': [],
                    'inputs': 2,
                    'outputs': 1,
                },
                'internal_flow_objects': [],
                'dependency_module_types': [],
                'compile_hints': {'supports_multi_instance': True},
                'source_info': {'original_subflow_id': 'random-subflow-id'},
            }
        ],
        'system_patterns': [
            {
                'pattern_id': 'ahu_ctrl__v1',
                'pattern_name': 'AHU control skeleton',
                'system_type': 'AHU',
            }
        ],
        'style_guides': [],
        'metadata': {
            'query_text': 'fan control',
            'query_variants': ['fan control', 'supply fan control'],
            'intent': 'general_query',
            'detected_operations': [],
            'selected_case_pattern_id': 'ahu_ctrl__v1',
            'retrieved_atomic_count': 1,
            'retrieved_subflow_count': 1,
            'retrieved_pattern_count': 1,
            'avg_atomic_score': 0.91,
            'query_bundle_version': 'phase2-v1',
        },
    }


def make_mixed_legacy_context():
    return {
        'query': 'fan control',
        'relevant_nodes': [
            {
                'module_type': 'constInput',
                'name': 'Constant Input',
                'category': 'logic/basic',
                'template_json': {'type': 'constInput', 'inputs': 0, 'outputs': 1},
                'similarity_score': 0.9,
            },
            {
                'module_type': 'fan_template',
                'name': 'Fan Template',
                'template_json': {'type': 'subflow', 'id': 'random-subflow-id', 'inputs': 2, 'outputs': 1},
                'similarity_score': 0.87,
            },
        ],
        'metadata': {
            'retrieved_count': 2,
            'avg_confidence_score': 0.885,
        },
    }


class RetrievalBundlePhase2Tests(unittest.TestCase):
    def test_workflow_state_includes_retrieval_bundle(self):
        self.assertIn('retrieval_bundle', workflow.WorkflowState.__annotations__)
        self.assertIn('retrieval_bundle', workflow_trace.WorkflowState.__annotations__)

    def test_workflow_run_initial_state_contains_retrieval_bundle(self):
        captured = {}

        class FakeApp:
            def invoke(self, initial_state, config=None):
                captured['initial_state'] = initial_state
                return initial_state

        class FakeWorkflow:
            def compile(self):
                return FakeApp()

        with patch.object(workflow, 'create_workflow', return_value=FakeWorkflow()):
            result = workflow.run_workflow('fan control')

        self.assertIn('retrieval_bundle', captured['initial_state'])
        self.assertEqual(captured['initial_state']['retrieval_bundle'], {})
        self.assertEqual(result['retrieval_bundle'], {})

    def test_workflow_trace_initial_state_contains_retrieval_bundle(self):
        captured = {}

        class FakeApp:
            def invoke(self, initial_state, config=None):
                captured['initial_state'] = initial_state
                return initial_state

        class FakeWorkflow:
            def compile(self):
                return FakeApp()

        with patch.object(workflow_trace, 'create_workflow', return_value=FakeWorkflow()), patch.object(workflow_trace, '_save_workflow_trace', return_value={'trace_dir': 'mock'}):
            result = workflow_trace.run_workflow('fan control')

        self.assertIn('retrieval_bundle', captured['initial_state'])
        self.assertEqual(captured['initial_state']['retrieval_bundle'], {})
        self.assertEqual(result['final_output']['workflow_trace']['trace_dir'], 'mock')

    def test_bundle_to_legacy_context(self):
        bundle = make_bundle()
        self.assertTrue(is_retrieval_bundle(bundle))

        legacy = build_legacy_retrieval_context(bundle)
        self.assertEqual(legacy['query'], 'fan control')
        self.assertEqual(len(legacy['relevant_nodes']), 1)
        self.assertEqual(legacy['relevant_nodes'][0]['module_type'], 'constInput')
        self.assertEqual(legacy['metadata']['retrieved_count'], 1)
        self.assertEqual(legacy['metadata']['avg_confidence_score'], 0.91)
        self.assertEqual(legacy['metadata']['query_variants_used'], 2)

    def test_compilable_doc_map_and_allowed_types(self):
        bundle = make_bundle()
        doc_map = build_compilable_doc_map(bundle)
        allowed_types = build_allowed_module_types(bundle)

        self.assertIn('constInput', doc_map)
        self.assertIn('fan_template', doc_map)
        self.assertEqual(doc_map['fan_template']['asset_type'], 'subflow_template')
        self.assertEqual(doc_map['fan_template']['template_json']['id'], 'fan_template')
        self.assertEqual(allowed_types, {'constInput', 'fan_template'})

    def test_mixed_legacy_context_stays_compatible(self):
        context = make_mixed_legacy_context()

        atomic_modules = get_atomic_modules(context)
        subflow_templates = get_subflow_templates(context)
        doc_map = build_compilable_doc_map(context)

        self.assertEqual([node['module_type'] for node in atomic_modules], ['constInput'])
        self.assertEqual([node['module_type'] for node in subflow_templates], ['fan_template'])
        self.assertEqual(set(doc_map.keys()), {'constInput', 'fan_template'})

    def test_load_structured_payload(self):
        payload = load_structured_payload({'payload_json': '{"name":"fan"}', 'json_schema': '{"name":"legacy"}'})
        self.assertEqual(payload['name'], 'fan')


if __name__ == '__main__':
    unittest.main()
