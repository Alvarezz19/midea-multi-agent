# Phase 2 retrieval bundle legacy / compat tests.

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.retrieval_bundle_utils import (
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


class RetrievalBundlePhase2CompatTests(unittest.TestCase):
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

    def test_mixed_legacy_context_stays_compatible(self):
        context = make_mixed_legacy_context()

        atomic_modules = get_atomic_modules(context)
        subflow_templates = get_subflow_templates(context)

        self.assertEqual([node['module_type'] for node in atomic_modules], ['constInput'])
        self.assertEqual([node['module_type'] for node in subflow_templates], ['fan_template'])

    def test_load_structured_payload(self):
        payload = load_structured_payload({'payload_json': '{"name":"fan"}', 'json_schema': '{"name":"legacy"}'})
        self.assertEqual(payload['name'], 'fan')
