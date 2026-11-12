import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import reports

ROOT = Path(__file__).resolve().parents[1]


def snapshot():
    return {
        'schema_version': 2, 'source': 'Aruba CMP via acloud 1.0.0',
        'started_at': '2026-11-12T10:00:00+00:00',
        'finished_at': '2026-11-12T10:01:00+00:00',
        'scope': {'account_label': 'example-account', 'project_id': None,
                  'endpoint_fingerprint': 'a' * 64},
        'selected_kinds': ['servers'], 'complete': True, 'errors': [],
        'projects': [{'project': {'metadata': {'id': 'project-a', 'name': 'Example'}},
                      'resources': {'servers': {'complete': True, 'count': 1, 'items': [
                          {'metadata': {'id': 'server-1', 'name': 'Web'},
                           'properties': {'status': {'state': 'Stopped'}, 'password': 'private-before'}}
                      ]}}}],
    }


def pair():
    before = snapshot()
    after = copy.deepcopy(before)
    after.update(started_at='2026-11-12T11:00:00+00:00', finished_at='2026-11-12T11:01:00+00:00')
    return before, after


class ReportTests(unittest.TestCase):
    def test_render_distinguishes_unknown_and_empty_and_legacy(self):
        data = snapshot()
        data['selected_kinds'] += ['volumes', 'ips']
        resources = data['projects'][0]['resources']
        resources['volumes'] = {'complete': True, 'count': 0, 'items': []}
        resources['ips'] = {'complete': False, 'count': None, 'items': None}
        data.update(complete=False, errors=[{'project_id': 'project-a', 'kind': 'ips', 'code': 'http_403'}])
        data['schema_version'] = 1
        del data['scope']
        text, code = reports.render(reports.validate(data))
        self.assertEqual(code, 2)
        self.assertIn('| Example | project\\-a | 1 | 0 | Unknown |', text)
        self.assertIn('http\\_403', text)
        self.assertNotIn('private-before', text)
        self.assertIn('legacy report', text)
        data['scope'] = ['ignored version 1 extension']
        self.assertEqual(reports.render(reports.validate(data))[0], text)

    def test_add_remove_modify_and_no_raw_values(self):
        before, after = pair()
        old = before['projects'][0]['resources']['servers']
        old['items'].append({'metadata': {'id': 'server-old'}})
        old['count'] = 2
        new = after['projects'][0]['resources']['servers']
        new['items'][0]['properties']['status']['state'] = 'Running'
        new['items'][0]['properties']['password'] = 'private-after'
        new['items'].append({'metadata': {'id': 'server-new'}})
        new['count'] = 2
        text, code = reports.diff(reports.validate(before), reports.validate(after))
        self.assertEqual(code, 0)
        self.assertIn('**Added:** 1', text)
        self.assertIn('**Removed:** 1', text)
        self.assertIn('**Modified:** 1', text)
        self.assertIn('/properties/status/state', text)
        self.assertNotIn('private-before', text)
        self.assertNotIn('private-after', text)

    def test_list_order_of_resources_and_dict_keys_do_not_create_changes(self):
        before, after = pair()
        item = {'metadata': {'id': 'server-2'}}
        for data in (before, after):
            family = data['projects'][0]['resources']['servers']
            family['items'].append(copy.deepcopy(item))
            family['count'] = 2
        after['projects'][0]['resources']['servers']['items'].reverse()
        after['projects'][0]['resources']['servers']['items'][1]['metadata'] = {'name': 'Web', 'id': 'server-1'}
        text, code = reports.diff(before, after)
        self.assertEqual(code, 0)
        self.assertIn('No resource changes observed', text)

    def test_partial_family_does_not_create_removals_and_other_family_still_compares(self):
        before, after = pair()
        for data in (before, after):
            data['selected_kinds'].append('volumes')
            data['projects'][0]['resources']['volumes'] = {
                'complete': True, 'count': 1, 'items': [{'metadata': {'id': 'volume-1'}}]}
        after['projects'][0]['resources']['servers'] = {'complete': False, 'count': None, 'items': None}
        after['projects'][0]['resources']['volumes'] = {'complete': True, 'count': 0, 'items': []}
        after.update(complete=False, errors=[{'project_id': 'project-a', 'kind': 'servers', 'code': 'http_403'}])
        text, code = reports.diff(reports.validate(before), reports.validate(after))
        self.assertEqual(code, 2)
        self.assertIn('volume\\-1 | Removed', text)
        self.assertNotIn('server\\-1 | Removed', text)
        self.assertIn('**Uncomparable scopes:** 1', text)

    def test_missing_project_is_visibility_change_not_resource_deletion(self):
        before, after = pair()
        after['projects'] = []
        text, code = reports.diff(before, after)
        self.assertEqual(code, 2)
        self.assertIn('No longer observed', text)
        self.assertIn('**Removed:** 0', text)

    def test_project_listing_failure_does_not_assert_visibility_changes(self):
        before, after = pair()
        after.update(projects=[], complete=False, errors=[{'scope': 'projects', 'code': 'http_403'}])
        text, code = reports.diff(before, after)
        self.assertEqual(code, 2)
        self.assertNotIn('| No longer observed |', text)
        self.assertIn('project visibility changes unverified', text)

    def test_incompatible_account_endpoint_project_source_kinds_and_time(self):
        mutations = [
            (lambda d: d['scope'].update(account_label=None), 'account_label_required'),
            (lambda d: d['scope'].update(account_label='another'), 'account_label_mismatch'),
            (lambda d: d['scope'].update(project_id='project-a'), 'project_scope_mismatch'),
            (lambda d: d['scope'].update(endpoint_fingerprint='b' * 64), 'endpoint_hint_mismatch'),
            (lambda d: d.update(source='Different source'), 'inventory_source_mismatch'),
            (lambda d: d.update(selected_kinds=['volumes']), 'resource_scope_mismatch'),
            (lambda d: d.update(started_at='2026-11-12T10:00:30+00:00'), 'overlapping_or_reversed_collections'),
            (lambda d: d.update(schema_version=1), 'scope_not_recorded'),
        ]
        for mutate, code in mutations:
            with self.subTest(code=code):
                before, after = pair()
                mutate(after)
                with self.assertRaisesRegex(reports.ReportError, '^' + code + '$'):
                    reports.diff(before, after)

    def test_structural_errors_rejected(self):
        mutations = [
            lambda d: d['projects'].append(copy.deepcopy(d['projects'][0])),
            lambda d: d['projects'][0]['resources']['servers'].update(count=4),
            lambda d: d['projects'][0]['resources']['servers']['items'].append(
                copy.deepcopy(d['projects'][0]['resources']['servers']['items'][0])),
            lambda d: d['projects'][0]['resources']['servers']['items'][0].update(metadata=[]),
            lambda d: d.update(complete=True, errors=[{'code': 'http_403'}]),
            lambda d: d.update(complete=False, errors=[{'project_id': 'project-a', 'kind': 'servers', 'code': 'http_403'}]),
            lambda d: d.update(started_at='not-a-date'),
            lambda d: d.update(started_at='2026-11-12T10:00:00'),
            lambda d: d.update(selected_kinds=['servers', 'servers']),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                data = snapshot()
                mutate(data)
                with self.assertRaises(reports.ReportError):
                    reports.validate(data)

    def test_names_cannot_inject_html_images_or_markdown_rows(self):
        data = snapshot()
        data['projects'][0]['project']['metadata']['name'] = '<img src="https://bad">\n![x](https://bad)|row'
        text, _ = reports.render(data)
        self.assertNotIn('<img', text)
        self.assertNotIn('![x](', text)
        self.assertIn('\\|row', text)
        self.assertNotIn('\n![', text)

    def test_json_pointer_paths_escape_slashes_and_tildes(self):
        self.assertEqual(reports.changed_paths({'a/b~': 1}, {'a/b~': 2}), ['/a~1b~0'])
        self.assertEqual(reports.changed_paths({'a': True}, {'a': 1}), ['/a'])
        self.assertEqual(reports.changed_paths({'a': [True]}, {'a': [1]}), ['/a/0'])
        self.assertEqual(reports.changed_paths({'a': [1, 2]}, {'a': [2, 1]}), ['/a/0', '/a/1'])

    def test_cli_works_without_binary_and_preserves_private_outputs_and_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            script = base / 'reports.py'
            script.write_bytes((ROOT / 'scripts/reports.py').read_bytes())
            before, after = pair()
            a, b = base / 'a.json', base / 'b.json'
            a.write_text(json.dumps(before)); b.write_text(json.dumps(after))
            original = (a.read_bytes(), b.read_bytes())
            out = base / 'report.md'
            cmd = [sys.executable, str(script), 'diff', str(a), str(b), '--output', str(out)]
            run = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(out.stat().st_mode & 0o777, 0o600)
            output = out.read_bytes()
            run = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(run.returncode, 2)
            self.assertEqual(out.read_bytes(), output)
            link = base / 'symlink.md'; link.symlink_to(out)
            run = subprocess.run(cmd[:-1] + [str(link)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 2)
            self.assertEqual(out.read_bytes(), output)
            self.assertEqual((a.read_bytes(), b.read_bytes()), original)

    def test_invalid_and_ambiguous_json_or_scope_do_not_create_output(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            inp, out = base / 'a.json', base / 'report.md'
            for body in ['{}', '{"schema_version":1,"schema_version":2}', '{"private": NaN}',
                         '{"private": 1e999}', '{bad']:
                inp.write_text(body)
                run = subprocess.run([sys.executable, str(ROOT / 'scripts/reports.py'), 'render',
                                      str(inp), '--output', str(out)], capture_output=True, text=True)
                self.assertEqual(run.returncode, 2)
                self.assertFalse(out.exists())
                self.assertNotIn('Traceback', run.stderr)
                self.assertNotIn('private', run.stderr)
            before, after = pair()
            after['scope']['account_label'] = 'other-account'
            inp.write_text(json.dumps(before))
            second = base / 'b.json'; second.write_text(json.dumps(after))
            run = subprocess.run([sys.executable, str(ROOT / 'scripts/reports.py'), 'diff',
                                  str(inp), str(second), '--output', str(out)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 2)
            self.assertFalse(out.exists())
            self.assertIn('account_label_mismatch', run.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
