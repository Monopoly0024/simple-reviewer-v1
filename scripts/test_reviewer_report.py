import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('reviewer_report.py')
spec = importlib.util.spec_from_file_location('reviewer_report', SCRIPT)
reviewer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reviewer)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'app.py').write_text('def run(): return 1\n', encoding='utf-8')
        (self.root / 'run.log').write_text('observed=1 expected=1\n', encoding='utf-8')
        digest = lambda name: hashlib.sha256((self.root / name).read_bytes()).hexdigest()
        self.record = {
            'schema_version': '1.0', 'title': 'Review', 'reviewed_at': '2026-10-21T12:00:00+08:00',
            'project_root': str(self.root), 'mode': 'review',
            'snapshot': {'base_revision': 'not-a-git-repository', 'notes': 'isolated fixture',
                         'files': [{'path': 'app.py', 'sha256': digest('app.py')}]},
            'requirements': [{'id': 'R1', 'text': 'Return one', 'source': 'user request',
                              'acceptance': 'Observed return value equals 1', 'required': True,
                              'status': 'passed', 'node_ids': ['N1'], 'evidence_ids': ['E1']}],
            'nodes': [{'id': 'N1', 'title': 'Return value', 'role': 'implemented',
                       'expected': 'Return 1', 'actual': 'Returns integer literal 1',
                       'input': 'none', 'output': 'integer', 'scope': 'unit execution only',
                       'status': 'passed', 'reason': 'Observed return value equals expectation',
                       'locations': [{'path': 'app.py', 'line': 1}],
                       'requirement_ids': ['R1'], 'evidence_ids': ['E1'], 'issue_ids': []}],
            'edges': [], 'issues': [],
            'evidence': [{'id': 'E1', 'kind': 'runtime', 'command': 'python app.py',
                          'cwd': '.', 'exit_code': 0, 'outcome': 'passed',
                          'expected': '1', 'observed': '1', 'scope': 'unit return value',
                          'source_files': ['app.py'], 'log_path': 'run.log',
                          'log_sha256': digest('run.log')}],
        }

    def assess(self):
        return reviewer.assess(self.record, self.root)

    def test_valid_runtime_evidence_passes(self):
        self.assertEqual(self.assess()['overall'], 'passed')

    def test_context_overview_has_effective_acceptance_and_escaped_text(self):
        self.record['user_goal'] = {'original_request': 'Show <script>alert(1)</script>',
                                    'plain_language': 'Return a value', 'open_questions': []}
        self.record['change_summary'] = {'baseline': 'working tree', 'files_modified': ['app.py'],
                                        'user_visible_changes': ['A visible <change>']}
        self.record['risks'] = [{'title': 'Example risk', 'action': 'Write a file',
            'status': 'not-run', 'impact': 'No file changed', 'next_step': 'Use an isolated fixture'}]
        self.record['next_actions'] = [{'action': 'Try empty input', 'reason': 'Boundary is unchecked'}]
        self.record['comprehension'] = {'glossary': [{'term': 'Unit test', 'meaning': 'Check one small part'}]}
        paths = reviewer.render(self.record, self.root, self.root / 'report')
        page = paths['overview_html'].read_text(encoding='utf-8')
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', page)
        self.assertNotIn('<script>alert(1)</script>', page)
        self.assertIn('Try empty input', page)
        self.assertIn('Example risk', page)
        self.assertIn('Observed return value equals 1', page)
        self.assertIn('已验证通过', page)
        self.assertIn('class="verdict passed"', page)
        self.assertIn('Check one small part', page)
        self.assertIn('Try empty input', paths['overview'].read_text(encoding='utf-8'))

    def test_open_goal_questions_prevent_overall_pass(self):
        self.record['user_goal'] = {'original_request': 'Return a value',
                                   'open_questions': ['Which value is actually required?']}
        self.assertEqual(self.assess()['overall'], 'unchecked')

    def test_context_invalid_action_state_is_rejected(self):
        self.record['risks'] = [{'title': 'Risk', 'action': 'Delete data', 'status': 'safe',
                                'impact': 'Unknown', 'next_step': 'Inspect first'}]
        with self.assertRaisesRegex(ValueError, 'status'):
            self.assess()

    def test_context_invalid_change_path_is_rejected(self):
        self.record['change_summary'] = {'files_modified': ['../outside.py']}
        with self.assertRaisesRegex(ValueError, 'outside|Outside'):
            self.assess()

    def test_null_context_is_rejected_with_validation_error(self):
        for key in ('user_goal', 'change_summary', 'risks', 'next_actions', 'comprehension'):
            with self.subTest(key=key):
                record = copy.deepcopy(self.record)
                record[key] = None
                with self.assertRaisesRegex(ValueError, key):
                    reviewer.assess(record, self.root)

    def test_old_record_overview_does_not_invent_context(self):
        page = reviewer.render(self.record, self.root, self.root / 'report')[
            'overview_html'].read_text(encoding='utf-8')
        self.assertIn('未提供原始需求原文', page)
        self.assertIn('未登记变更说明', page)
        self.assertIn('未登记风险检查', page)
        self.assertNotIn('>没有风险<', page)

    def test_overview_uses_downgraded_evidence(self):
        (self.root / 'app.py').write_text('def run(): return 2\n', encoding='utf-8')
        page = reviewer.render(self.record, self.root, self.root / 'report')[
            'overview_html'].read_text(encoding='utf-8')
        self.assertIn('未验证', page)
        self.assertIn('证据已过期，待复验', page)
        self.assertNotIn('class="acceptance passed"', page)

    def test_overview_cannot_overwrite_source(self):
        source = self.root / 'reviewer-overview.html'
        source.write_text('original', encoding='utf-8')
        self.record['snapshot']['files'].append({'path': source.name,
            'sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            reviewer.render(self.record, self.root, self.root)
        self.assertEqual(source.read_text(encoding='utf-8'), 'original')

    def test_bundled_example_evidence_survives_lf_checkout(self):
        assets = SCRIPT.parent.parent / 'assets'
        fixture = self.root / 'example'
        fixture.mkdir()
        record = json.loads((assets / 'review.example.json').read_text(encoding='utf-8'))
        for path in (assets / 'order-export').iterdir():
            if path.is_file():
                (fixture / path.name).write_bytes(path.read_bytes().replace(b'\r\n', b'\n'))
        record['project_root'] = str(fixture)
        result = reviewer.assess(record, self.root)
        self.assertEqual(result['stale_files'], [])
        self.assertEqual(result['stale_evidence'], [])
        self.assertEqual(result['overall'], 'failed')

    def test_static_reading_cannot_turn_node_green(self):
        self.record['evidence'][0]['kind'] = 'static'
        with self.assertRaisesRegex(ValueError, 'runtime'):
            self.assess()

    def test_source_change_invalidates_previous_pass(self):
        (self.root / 'app.py').write_text('def run(): return 2\n', encoding='utf-8')
        result = self.assess()
        self.assertEqual(result['nodes'][0]['status'], 'pending')
        self.assertEqual(result['requirements'][0]['status'], 'unchecked')
        self.assertEqual(result['overall'], 'unchecked')

    def test_tampered_log_invalidates_previous_pass(self):
        (self.root / 'run.log').write_text('changed\n', encoding='utf-8')
        result = self.assess()
        self.assertEqual(result['overall'], 'unchecked')
        self.assertTrue(result['stale_evidence'])

    def test_failure_is_not_hidden_by_other_success(self):
        self.record['nodes'][0]['status'] = 'failed'
        self.record['nodes'][0]['issue_ids'] = ['I1']
        self.record['requirements'][0]['status'] = 'failed'
        self.record['evidence'][0]['outcome'] = 'failed'
        self.record['issues'] = [{'id': 'I1', 'title': 'Wrong result', 'status': 'confirmed',
                                  'severity': 'blocking', 'node_ids': ['N1'], 'evidence_ids': ['E1'],
                                  'impact': 'Wrong answer', 'suggestion': 'Fix return value'}]
        self.assertEqual(self.assess()['overall'], 'failed')

    def test_unverified_required_goal_prevents_overall_pass(self):
        self.record['requirements'].append({'id': 'R2', 'text': 'Download', 'source': 'user request',
            'acceptance': 'File can be downloaded', 'required': True, 'status': 'unchecked',
            'node_ids': ['N1'], 'evidence_ids': []})
        self.assertEqual(self.assess()['overall'], 'unchecked')

    def test_passed_goal_cannot_hide_unverified_node(self):
        self.record['nodes'][0]['status'] = 'unchecked'
        self.record['nodes'][0]['evidence_ids'] = []
        with self.assertRaisesRegex(ValueError, 'node'):
            self.assess()

    def test_dangling_edge_is_rejected(self):
        self.record['edges'] = [{'source': 'N1', 'target': 'N9', 'kind': 'normal', 'label': ''}]
        with self.assertRaises(ValueError):
            self.assess()

    def test_source_path_cannot_escape_project(self):
        self.record['snapshot']['files'][0]['path'] = '../private.txt'
        with self.assertRaisesRegex(ValueError, 'project'):
            self.assess()

    def test_missing_node_requires_confirmed_evidence(self):
        self.record['nodes'][0]['role'] = 'missing'
        with self.assertRaises(ValueError):
            self.assess()

    def test_generator_is_read_only_and_preserves_input(self):
        original = copy.deepcopy(self.record)
        reviewer.render(self.record, self.root, self.root / 'report')
        self.assertEqual(self.record, original)
        self.assertEqual((self.root / 'app.py').read_text(encoding='utf-8'), 'def run(): return 1\n')

    def test_html_cannot_execute_injected_title(self):
        self.record['title'] = '</script><script>alert(1)</script>'
        paths = reviewer.render(self.record, self.root, self.root / 'report')
        html = paths['html'].read_text(encoding='utf-8')
        self.assertNotIn('</script><script>alert(1)</script>', html)
        self.assertIn('textContent', html)
        illustrated = paths['breakdown_html'].read_text(encoding='utf-8')
        self.assertNotIn('</script><script>alert(1)</script>', illustrated)
        self.assertIn('&lt;/script&gt;', illustrated)

    def test_output_includes_colored_graph_and_verifiable_details(self):
        paths = reviewer.render(self.record, self.root, self.root / 'report')
        markdown = paths['markdown'].read_text(encoding='utf-8')
        self.assertIn('```mermaid', markdown)
        self.assertIn('class N1 passed', markdown)
        self.assertIn('python app.py', markdown)
        self.assertIn('app.py:1', markdown)

    def test_duplicate_ids_are_rejected(self):
        self.record['nodes'].append(copy.deepcopy(self.record['nodes'][0]))
        with self.assertRaises(ValueError):
            self.assess()

    def test_green_node_cannot_hide_failed_linked_evidence(self):
        failed = copy.deepcopy(self.record['evidence'][0])
        failed.update(id='E2', outcome='failed')
        self.record['evidence'].append(failed)
        self.record['nodes'][0]['evidence_ids'].append('E2')
        with self.assertRaisesRegex(ValueError, 'failed|blocked'):
            self.assess()

    def test_unprovided_node_cannot_be_green(self):
        self.record['nodes'][0]['role'] = 'unprovided'
        with self.assertRaisesRegex(ValueError, 'unprovided'):
            self.assess()

    def test_render_always_produces_standalone_breakdown(self):
        paths = reviewer.render(self.record, self.root, self.root / 'report')
        self.assertEqual(len(paths), 7)
        self.assertIn('breakdown', paths)
        self.assertIn('breakdown_html', paths)
        doc = paths['breakdown'].read_text(encoding='utf-8')
        for value in ('Return value', 'Return 1', 'Returns integer literal 1',
                      'unit execution only', 'python app.py', 'app.py:1'):
            self.assertIn(value, doc)
        page = paths['breakdown_html'].read_text(encoding='utf-8')
        for value in ('Return value', 'Return 1', 'app.py:1', '已验证通过',
                      'role="button"', 'code-line'):
            self.assertIn(value, page)

    def test_breakdown_html_escapes_source_and_record_text(self):
        source = self.root / 'app.py'
        source.write_text('def run(): return "<unsafe>"\n', encoding='utf-8')
        self.record['snapshot']['files'][0]['sha256'] = hashlib.sha256(
            source.read_bytes()).hexdigest()
        self.record['nodes'][0]['actual'] = '<unsafe> is returned'
        paths = reviewer.render(self.record, self.root, self.root / 'report')
        page = paths['breakdown_html'].read_text(encoding='utf-8')
        self.assertIn('&lt;unsafe&gt;', page)
        self.assertNotIn('<unsafe>', page)
        self.assertIn('code-line', page)

    def test_illustration_is_structured_and_escaped(self):
        self.record['blocks'] = [{'id': 'B1', 'title': 'Service', 'purpose': 'Return value',
            'node_ids': ['N1'], 'explanation': {'summary': 'A small <service>',
            'steps': [{'title': 'Return', 'detail': 'Use the literal 1'}],
            'example': {'input': 'No arguments', 'expected': '1', 'note': 'Illustration only'}}}]
        page = reviewer.render(self.record, self.root, self.root / 'report')[
            'breakdown_html'].read_text(encoding='utf-8')
        self.assertIn('A small &lt;service&gt;', page)
        self.assertIn('Use the literal 1', page)
        self.assertIn('Illustration only', page)

    def test_invalid_explanation_is_rejected(self):
        self.record['blocks'] = [{'id': 'B1', 'title': 'Service', 'purpose': 'Return',
            'node_ids': ['N1'], 'explanation': {'steps': '<script>bad()</script>'}}]
        with self.assertRaisesRegex(ValueError, 'steps'):
            self.assess()

    def test_source_excerpt_marks_changed_and_invalid_ranges(self):
        (self.root / 'app.py').write_text('def run(): return 2\n', encoding='utf-8')
        self.record['nodes'][0]['locations'][0]['end_line'] = 99
        page = reviewer.render(self.record, self.root, self.root / 'report')[
            'breakdown_html'].read_text(encoding='utf-8')
        self.assertIn('源码已变化', page)
        self.assertIn('位置超出当前文件', page)
        self.assertIn('class="block pending"', page)
        self.assertNotIn('class="block passed"', page)

    def test_html_cannot_overwrite_reviewed_source(self):
        source = self.root / 'code-breakdown.html'
        source.write_text('original\n', encoding='utf-8')
        self.record['snapshot']['files'].append({'path': source.name,
            'sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            reviewer.render(self.record, self.root, self.root, breakdown_only=True)
        self.assertEqual(source.read_text(encoding='utf-8'), 'original\n')

    def test_excerpt_limit_keeps_full_range_visible(self):
        source = self.root / 'app.py'
        source.write_text('\n'.join(f'value_{n} = {n}' for n in range(1, 151)), encoding='utf-8')
        self.record['snapshot']['files'][0]['sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
        self.record['nodes'][0]['locations'][0]['end_line'] = 150
        page = reviewer.render(self.record, self.root, self.root / 'report')[
            'breakdown_html'].read_text(encoding='utf-8')
        self.assertIn('app.py:1–150', page)
        self.assertIn('value_120 = 120', page)
        self.assertNotIn('value_121 = 121', page)
        self.assertIn('仅展示前 120 行', page)

    def test_missing_source_has_no_old_green_or_invented_excerpt(self):
        (self.root / 'app.py').unlink()
        page = reviewer.render(self.record, self.root, self.root / 'report')[
            'breakdown_html'].read_text(encoding='utf-8')
        self.assertIn('源码缺失或不是 UTF-8', page)
        self.assertIn('class="block pending"', page)
        self.assertNotIn('def run():', page)

    def test_template_markers_in_text_are_not_replaced_again(self):
        self.record['title'] = 'Literal @@CONTENT@@ <text>'
        page = reviewer.render(self.record, self.root, self.root / 'report')[
            'breakdown_html'].read_text(encoding='utf-8')
        self.assertIn('Literal @@CONTENT@@ &lt;text&gt;', page)

    def test_tampered_log_downgrades_html_without_claiming_source_changed(self):
        (self.root / 'run.log').write_text('changed\n', encoding='utf-8')
        page = reviewer.render(self.record, self.root, self.root / 'report')[
            'breakdown_html'].read_text(encoding='utf-8')
        self.assertIn('class="block pending"', page)
        self.assertIn('证据已过期', page)
        self.assertNotIn('源码已变化', page)

    def test_breakdown_command_writes_markdown_and_html(self):
        record = self.root / 'review.json'
        record.write_text(json.dumps(self.record), encoding='utf-8')
        out = self.root / 'breakdown-only'
        result = subprocess.run([sys.executable, '-B', str(SCRIPT), 'breakdown', str(record),
                                 '--out', str(out)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(p.name for p in out.iterdir()),
                         ['code-breakdown.html', 'code-breakdown.md'])

    def test_block_groups_multiple_nodes_and_locations(self):
        self.record['nodes'][0]['locations'][0].update(symbol='run', end_line=1)
        extra = copy.deepcopy(self.record['nodes'][0])
        extra.update(id='N2', title='Independent return contract')
        self.record['nodes'].append(extra)
        self.record['blocks'] = [{'id': 'B1', 'title': 'Application service',
            'purpose': 'Expose a stable return value', 'node_ids': ['N1', 'N2']}]
        paths = reviewer.render(self.record, self.root, self.root / 'report')
        doc = paths['breakdown'].read_text(encoding='utf-8')
        self.assertIn('Application service', doc)
        self.assertIn('Expose a stable return value', doc)
        self.assertIn('run', doc)
        self.assertIn('N1', doc)
        self.assertIn('N2', doc)
        self.assertIn('[app.py:1 · run](<', doc)
        self.assertIn(':1>)', doc)

    def test_breakdown_does_not_reuse_stale_green(self):
        (self.root / 'app.py').write_text('def run(): return 2\n', encoding='utf-8')
        paths = reviewer.render(self.record, self.root, self.root / 'report')
        doc = paths['breakdown'].read_text(encoding='utf-8')
        self.assertIn('待核实', doc)
        self.assertNotIn('class B1 passed;', doc)

    def test_block_cannot_omit_a_node(self):
        self.record['blocks'] = [{'id': 'B1', 'title': 'Empty', 'purpose': 'None', 'node_ids': []}]
        with self.assertRaises(ValueError):
            self.assess()

    def test_block_cannot_reference_unknown_node(self):
        self.record['blocks'] = [{'id': 'B1', 'title': 'Unknown', 'purpose': 'None', 'node_ids': ['N9']}]
        with self.assertRaises(ValueError):
            self.assess()

    def test_duplicate_block_membership_is_rejected(self):
        self.record['blocks'] = [
            {'id': 'B1', 'title': 'One', 'purpose': 'Return', 'node_ids': ['N1']},
            {'id': 'B2', 'title': 'Two', 'purpose': 'Return', 'node_ids': ['N1']}]
        with self.assertRaises(ValueError):
            self.assess()

    def test_invalid_location_range_is_rejected(self):
        self.record['nodes'][0]['locations'][0]['end_line'] = 0
        with self.assertRaises(ValueError):
            self.assess()

    def test_breakdown_cannot_overwrite_reviewed_source(self):
        source = self.root / 'code-breakdown.md'
        source.write_text('original source\n', encoding='utf-8')
        self.record['snapshot']['files'].append({'path': source.name,
            'sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
        with self.assertRaises(ValueError):
            reviewer.render(self.record, self.root, self.root)
        self.assertEqual(source.read_text(encoding='utf-8'), 'original source\n')


if __name__ == '__main__':
    unittest.main(verbosity=2)
