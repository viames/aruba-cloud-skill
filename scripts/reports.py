#!/usr/bin/env python3
"""Render private inventory summaries and compare snapshots offline. Python stdlib only."""
import argparse
import datetime
import html
import json
import math
import os
from pathlib import Path
import re
import sys

KINDS = ('servers', 'volumes', 'vpcs', 'ips', 'dbaas', 'kaas', 'registries')


class ReportError(ValueError):
    """A diagnostic code safe to print without echoing input data."""


def require(condition, code='invalid_inventory_schema'):
    if not condition:
        raise ReportError(code)


def identifier(value):
    return isinstance(value, str) and bool(value.strip())


def timestamp(value):
    require(isinstance(value, str))
    try:
        result = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ReportError('invalid_inventory_timestamp') from None
    require(result.tzinfo is not None, 'invalid_inventory_timestamp')
    return result


def validate(data):
    require(isinstance(data, dict))
    version = data.get('schema_version')
    require(type(version) is int and version in (1, 2), 'unsupported_inventory_version')
    kinds = data.get('selected_kinds')
    require(isinstance(kinds, list) and bool(kinds))
    require(all(isinstance(k, str) and k in KINDS for k in kinds))
    require(len(set(kinds)) == len(kinds))
    require(type(data.get('complete')) is bool and identifier(data.get('source')))
    require(timestamp(data.get('started_at')) <= timestamp(data.get('finished_at')),
            'invalid_inventory_timestamp')
    require(isinstance(data.get('projects'), list) and isinstance(data.get('errors'), list))
    require(all(isinstance(e, dict) for e in data['errors']))
    if version == 2:
        scope = data.get('scope')
        require(isinstance(scope, dict))
        require('account_label' in scope and 'project_id' in scope)
        require(scope['account_label'] is None or identifier(scope['account_label']))
        require(scope['project_id'] is None or identifier(scope['project_id']))
        require(isinstance(scope.get('endpoint_fingerprint'), str) and
                re.fullmatch(r'[a-f0-9]{64}', scope['endpoint_fingerprint']) is not None)
    seen, failed, failed_scopes = set(), False, set()
    for entry in data['projects']:
        require(isinstance(entry, dict) and isinstance(entry.get('project'), dict))
        meta = entry['project'].get('metadata')
        require(isinstance(meta, dict) and identifier(meta.get('id')))
        require(meta['id'] not in seen, 'duplicate_project_id')
        seen.add(meta['id'])
        resources = entry.get('resources')
        require(isinstance(resources, dict) and set(resources) == set(kinds))
        for family in resources.values():
            require(isinstance(family, dict) and type(family.get('complete')) is bool)
            if not family['complete']:
                failed = True
                require(family.get('count') is None and family.get('items') is None)
                continue
            items = family.get('items')
            require(isinstance(items, list) and type(family.get('count')) is int)
            require(family['count'] == len(items), 'inventory_count_mismatch')
            ids = set()
            for item in items:
                require(isinstance(item, dict) and isinstance(item.get('metadata'), dict))
                resource_id = item['metadata'].get('id')
                require(identifier(resource_id))
                require(resource_id not in ids, 'duplicate_resource_id')
                ids.add(resource_id)
        failed_scopes.update((meta['id'], kind) for kind, family in resources.items() if not family['complete'])
    error_scopes = set()
    for error in data['errors']:
        require(isinstance(error.get('code'), str))
        if error.get('scope') == 'projects':
            continue
        require(identifier(error.get('project_id')) and error.get('kind') in kinds)
        key = (error['project_id'], error['kind'])
        require(key in failed_scopes, 'inconsistent_error_scope')
        error_scopes.add(key)
    require(failed_scopes == error_scopes, 'inconsistent_error_scope')
    require(data['complete'] == (not data['errors'] and not failed), 'inconsistent_completeness')
    if version == 2 and data['scope']['project_id'] is not None:
        require(seen == {data['scope']['project_id']}, 'inconsistent_project_scope')
    return data


def read_inventory(path):
    try:
        # Duplicate JSON keys can conceal contradictory scope or completeness values.
        def unique(pairs):
            result = {}
            for key, value in pairs:
                require(key not in result, 'duplicate_json_key')
                result[key] = value
            return result
        def finite(value):
            result = float(value)
            require(math.isfinite(result), 'invalid_json_number')
            return result
        def constant(_):
            raise ReportError('invalid_json_number')
        return validate(json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique,
                                   parse_float=finite, parse_constant=constant))
    except ReportError:
        raise
    except (ValueError, UnicodeError):
        raise ReportError('invalid_inventory_json') from None


def cell(value):
    """Keep resource names/IDs as text, never links, images, HTML, or table syntax."""
    value = ''.join(c if c.isprintable() else ' ' for c in str(value))
    value = html.escape(value, quote=True)
    return re.sub(r'([\\`*_{}\[\]()#+.!|~\-])', r'\\\1', value)


def table(headers, rows):
    return ['| ' + ' | '.join(headers) + ' |',
            '| ' + ' | '.join('---' for _ in headers) + ' |',
            *['| ' + ' | '.join(cell(v) for v in row) + ' |' for row in rows], '']


def project_name(entry):
    meta = entry['project']['metadata']
    return meta.get('name') if identifier(meta.get('name')) else meta['id']


def diagnostics(data):
    lines = []
    for error in data['errors']:
        code = error.get('code', '')
        if not isinstance(code, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,79}', code):
            code = 'unrecognized_diagnostic'
        is_projects = error.get('scope') == 'projects'
        lines.append(('projects' if is_projects else error['project_id'],
                      'projects' if is_projects else error['kind'], code))
    return table(['Scope', 'Family', 'Diagnostic'], lines) if lines else ['None.', '']


def render(data):
    scope = data['scope'] if data['schema_version'] == 2 else {}
    kinds = [k for k in KINDS if k in data['selected_kinds']]
    lines = ['# Aruba Cloud inventory', '',
             f'**Collection:** {cell(data["started_at"])} to {cell(data["finished_at"])}', '',
             f'**Status:** {"Complete for selected scope" if data["complete"] else "Incomplete — unknown results remain"}', '',
             f'**Account label:** {cell(scope.get("account_label") or "Not recorded")}', '',
             f'**Project scope:** {cell(scope.get("project_id") or ("All visible projects" if scope else "Not recorded (legacy report)"))}', '',
             'Counts refer to observed resources, not costs, health, or utilization. '
             'Unknown means inaccessible or uncollected; it is not zero.', '']
    rows = []
    for entry in sorted(data['projects'], key=lambda e: e['project']['metadata']['id']):
        rows.append([project_name(entry), entry['project']['metadata']['id'],
                     *[entry['resources'][k]['count'] if entry['resources'][k]['complete'] else 'Unknown'
                       for k in kinds]])
    lines += table(['Project', 'Project ID', *kinds], rows)
    known = sum(f['count'] for e in data['projects'] for f in e['resources'].values() if f['complete'])
    unknown = sum(not f['complete'] for e in data['projects'] for f in e['resources'].values())
    lines += [f'**Observed resources in completed collections:** {known}. '
              f'**Unknown project/family collections:** {unknown}.', '',
              '**Project discovery:** ' + (
                  'Not recorded (legacy report).' if not scope else
                  'Not performed (explicit project selection).' if scope.get('project_id') else
                  'Incomplete; additional projects may be unobserved.' if any(e.get('scope') == 'projects' for e in data['errors']) else
                  'Complete within the visible scope.'), '',
              '## Diagnostics', '', *diagnostics(data),
              'Private infrastructure metadata. Keep this report private. A scan is not an atomic snapshot. '
              'Account labels are supplied by the operator, not authenticated account IDs.', '']
    return '\n'.join(lines), 0 if data['complete'] else 2


def compatible(before, after):
    require(before['schema_version'] == after['schema_version'] == 2, 'scope_not_recorded')
    a, b = before['scope'], after['scope']
    require(identifier(a['account_label']) and identifier(b['account_label']), 'account_label_required')
    require(a['account_label'] == b['account_label'], 'account_label_mismatch')
    require(a['project_id'] == b['project_id'], 'project_scope_mismatch')
    require(a['endpoint_fingerprint'] == b['endpoint_fingerprint'], 'endpoint_hint_mismatch')
    require(before['source'] == after['source'], 'inventory_source_mismatch')
    require(set(before['selected_kinds']) == set(after['selected_kinds']), 'resource_scope_mismatch')
    require(timestamp(before['finished_at']) <= timestamp(after['started_at']),
            'overlapping_or_reversed_collections')


def changed_paths(before, after, path=''):
    if type(before) is not type(after):
        return [path or '/']
    if isinstance(before, dict):
        paths = []
        for key in sorted(before.keys() | after.keys()):
            pointer = path + '/' + key.replace('~', '~0').replace('/', '~1')
            paths.extend([pointer] if key not in before or key not in after else
                         changed_paths(before[key], after[key], pointer))
        return paths
    if isinstance(before, list):
        if len(before) != len(after):
            return [path or '/']
        return [p for index, (a, b) in enumerate(zip(before, after))
                for p in changed_paths(a, b, path + '/' + str(index))]
    # Preserve list ordering: its meaning is service-specific. Show paths, never raw values.
    return [path or '/'] if before != after else []


def diff(before, after):
    compatible(before, after)
    lines = ['# Aruba Cloud inventory changes', '',
             f'**Account label:** {cell(before["scope"]["account_label"])}', '',
             f'**Before finished:** {cell(before["finished_at"])}', '',
             f'**After started:** {cell(after["started_at"])}', '',
             'Changes describe observations in two inventories. Absence does not prove cloud deletion. '
             'Matching operator labels and endpoint hints do not verify account identity or unchanged permissions.', '']
    projects_a = {e['project']['metadata']['id']: e for e in before['projects']}
    projects_b = {e['project']['metadata']['id']: e for e in after['projects']}
    project_errors = any(e.get('scope') == 'projects' for d in (before, after) for e in d['errors'])
    changes, unknown, project_rows = [], [], []
    for project in sorted(projects_a.keys() | projects_b.keys()):
        if project not in projects_a or project not in projects_b:
            project_rows.append((project, 'Newly observed' if project in projects_b else 'No longer observed'))
            unknown.append((project, 'all selected', 'Project not observed in both inventories'))
            continue
        for kind in KINDS:
            if kind not in before['selected_kinds']:
                continue
            a, b = projects_a[project]['resources'][kind], projects_b[project]['resources'][kind]
            if project_errors or not a['complete'] or not b['complete']:
                unknown.append((project, kind, 'Project listing or resource collection incomplete'))
                continue
            items_a = {item['metadata']['id']: item for item in a['items']}
            items_b = {item['metadata']['id']: item for item in b['items']}
            for resource in sorted(items_a.keys() | items_b.keys()):
                if resource not in items_a:
                    changes.append((project, kind, resource, 'Added', ''))
                elif resource not in items_b:
                    changes.append((project, kind, resource, 'Removed', ''))
                else:
                    paths = changed_paths(items_a[resource], items_b[resource])
                    if paths:
                        shown = ', '.join(paths[:20])
                        if len(paths) > 20:
                            shown += f' (+{len(paths) - 20} more paths)'
                        changes.append((project, kind, resource, 'Modified', shown))
    if project_errors:
        unknown.append(('projects', 'project discovery', 'Project listing incomplete; project visibility changes unverified'))
        project_rows = []
    incomplete = not before['complete'] or not after['complete'] or bool(unknown)
    totals = {kind: sum(row[3] == kind for row in changes) for kind in ('Added', 'Removed', 'Modified')}
    lines += [f'**Result:** {"Partial comparison" if incomplete else "Complete comparison for selected scope"}', '',
              f'**Added:** {totals["Added"]} · **Removed:** {totals["Removed"]} · '
              f'**Modified:** {totals["Modified"]} · **Uncomparable scopes:** {len(unknown)}', '',
              '## Resource observations', '']
    lines += table(['Project ID', 'Family', 'Resource ID', 'Observation', 'Changed field paths'], changes) if changes else ['No resource changes observed in comparable scopes.', '']
    lines += ['Field paths use JSON Pointer notation. Raw property values are omitted. '
              'Metadata and status changes are included; the comparison does not infer an operator action.', '',
              '## Project visibility', '']
    lines += table(['Project ID', 'Observation'], project_rows) if project_rows else ['No verified project visibility changes.', '']
    lines += ['## Uncomparable scopes', '']
    lines += table(['Project ID', 'Family', 'Reason'], unknown) if unknown else ['None.', '']
    for label, data in [('Before', before), ('After', after)]:
        if data['errors']:
            lines += [f'## {label} diagnostics', '', *diagnostics(data)]
    lines += ['Private infrastructure metadata. Both scans are non-atomic observations; '
              'unobserved scopes must not be interpreted as unchanged.', '']
    return '\n'.join(lines), 2 if incomplete else 0


def write_private(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    summary = sub.add_parser('render', help='Render an inventory JSON as private Markdown')
    summary.add_argument('inventory')
    summary.add_argument('--output', required=True)
    compare = sub.add_parser('diff', help='Compare two labeled inventories as private Markdown')
    compare.add_argument('before')
    compare.add_argument('after')
    compare.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'render':
            text, code = render(read_inventory(args.inventory))
        else:
            text, code = diff(read_inventory(args.before), read_inventory(args.after))
        write_private(args.output, text)
        print(json.dumps({'output': str(Path(args.output).resolve()), 'complete': code == 0}))
        return code
    except ReportError as error:
        print(str(error), file=sys.stderr)
        return 2
    except (OSError, UnicodeError, RecursionError):
        print('report_io_or_encoding_error', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
