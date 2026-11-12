#!/usr/bin/env python3
"""Read-only Aruba CMP inventory through the pinned official CLI. Python stdlib only."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
from install_cli import platform_key
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / 'bin' / 'acloud'
KINDS = {
    'servers': ('compute', 'cloudserver', 'No cloud servers found'),
    'volumes': ('storage', 'blockstorage', 'No block storage found'),
    'vpcs': ('network', 'vpc', 'No VPCs found'),
    'ips': ('network', 'elasticip', 'No Elastic IPs found'),
    'dbaas': ('database', 'dbaas', 'No DBaaS instances found'),
    'kaas': ('container', 'kaas', 'No KaaS clusters found'),
    'registries': ('container', 'containerregistry', 'No container registries found'),
}


class CollectionError(Exception):
    pass


def verify_binary():
    provenance = json.loads((ROOT / 'references' / 'provenance.json').read_text())
    receipt = json.loads((ROOT / 'bin' / 'install.json').read_text())
    target = platform_key()
    if receipt['platform'] != target or receipt['cli_version'] != provenance['cli_version']:
        raise CollectionError('installed_cli_platform_or_version_mismatch')
    if receipt['archive_sha256'] != provenance['artifacts'][target]['sha256']:
        raise CollectionError('installed_archive_checksum_mismatch')
    if hashlib.sha256(BIN.read_bytes()).hexdigest() != receipt['binary_sha256']:
        raise CollectionError('binary_checksum_mismatch')
    return provenance


def invoke(args, profile=None, timeout=30):
    command = [str(BIN), '--timeout', f'{timeout}s']
    if profile:
        command += ['--profile', profile]
    command += args
    try:
        result = subprocess.run(command, text=True, capture_output=True,
                                timeout=timeout + 5, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise CollectionError('cli_timeout') from None
    if result.returncode:
        # Never echo untrusted error bodies: an auth response may contain secrets.
        code = 'cli_failed'
        for status in ('401', '403', '404', '429', '500', '502', '503'):
            if status in result.stderr:
                code = f'http_{status}'
                break
        raise CollectionError(code)
    return result.stdout.strip()


def collect(domain, resource, empty, profile, project, limit, max_pages, timeout):
    """Offset pagination; fail closed on duplicate items, drift, or malformed data."""
    items, seen = [], set()
    offset, expected_total = 0, None
    for _ in range(max_pages):
        args = [domain, resource, 'list', '-o', 'json', '--limit', str(limit),
                '--offset', str(offset)]
        if project:
            args += ['--project-id', project]
        raw = invoke(args, profile, timeout)
        if raw == empty:
            if expected_total is not None and len(items) < expected_total:
                raise CollectionError('pagination_ended_before_total')
            return items
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise CollectionError('unexpected_cli_output') from None
        if not isinstance(data, dict) or not isinstance(data.get('values'), list):
            raise CollectionError('unexpected_list_schema')
        batch = data['values']
        total = data.get('total')
        if type(total) is not int or total < 0:
            raise CollectionError('invalid_total')
        if expected_total is not None and total != expected_total:
            raise CollectionError('inventory_changed_during_pagination')
        expected_total = total
        if not batch:
            if len(items) < total or data.get('next'):
                raise CollectionError('pagination_ended_before_total')
            return items
        for item in batch:
            if not isinstance(item, dict):
                raise CollectionError('unexpected_item_schema')
            identity = item.get('metadata', {}).get('id')
            if not isinstance(identity, str) or not identity:
                raise CollectionError('missing_resource_id')
            if identity in seen:
                raise CollectionError('duplicate_or_repeated_page')
            seen.add(identity)
            items.append(item)
        offset += len(batch)
        # Some APIs omit total/next. Probe an empty page instead of assuming completeness.
        if total > 0 and offset >= total and not data.get('next'):
            if offset != total:
                raise CollectionError('inconsistent_total')
            return items
    raise CollectionError('pagination_limit_reached')


def inventory(args):
    report = {
        'schema_version': 2,
        'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'source': 'Aruba CMP via acloud 1.0.0',
        'profile': args.profile or os.environ.get('ACLOUD_PROFILE') or '(CLI active/default)',
        'credential_env_override': bool(os.environ.get('ACLOUD_CLIENT_ID') or
                                        os.environ.get('ACLOUD_CLIENT_SECRET')),
        'selected_kinds': args.kinds.split(','),
        'scope': {
            'account_label': args.account_label,
            'project_id': args.project_id,
            # An endpoint hint, not proof of the effective account or configuration.
            # Hash the hints so URL credentials/query strings cannot enter reports.
            'endpoint_fingerprint': hashlib.sha256(json.dumps([
                os.environ.get('ACLOUD_BASE_URL'),
                os.environ.get('ACLOUD_TOKEN_ISSUER_URL'),
            ]).encode()).hexdigest(),
        },
        'complete': True, 'projects': [], 'errors': [],
    }
    try:
        projects = ([{'metadata': {'id': args.project_id}}] if args.project_id else
                    collect('management', 'project', 'No projects found', args.profile,
                            None, args.page_size, args.max_pages, args.timeout))
    except CollectionError as e:
        projects = []
        report['errors'].append({'scope': 'projects', 'code': str(e)})
    for project in projects:
        project_id = project['metadata']['id']
        entry = {'project': project, 'resources': {}}
        report['projects'].append(entry)
        for kind in report['selected_kinds']:
            domain, resource, empty = KINDS[kind]
            try:
                values = collect(domain, resource, empty, args.profile, project_id,
                                 args.page_size, args.max_pages, args.timeout)
                entry['resources'][kind] = {'complete': True, 'count': len(values),
                                             'items': values}
            except CollectionError as e:
                entry['resources'][kind] = {'complete': False, 'count': None, 'items': None}
                report['errors'].append({'project_id': project_id, 'kind': kind,
                                         'code': str(e)})
    report['complete'] = not report['errors']
    report['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    # O_EXCL refuses overwrite and symlinks. File is private from creation onward.
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
    print(json.dumps({'output': str(Path(args.output).resolve()),
                      'complete': report['complete'], 'projects': len(projects),
                      'errors': len(report['errors'])}))
    return 0 if report['complete'] else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor', help='Offline verification; never prints secrets')
    inv = sub.add_parser('inventory', help='Read-only paginated inventory')
    inv.add_argument('--profile')
    inv.add_argument('--account-label', help='Stable non-secret label for one account; needed for offline diffs')
    inv.add_argument('--project-id')
    inv.add_argument('--kinds', default=','.join(KINDS))
    inv.add_argument('--page-size', type=int, default=50)
    inv.add_argument('--max-pages', type=int, default=1000)
    inv.add_argument('--timeout', type=int, default=30)
    inv.add_argument('--output', required=True, help='New private JSON file; parent must exist')
    args = parser.parse_args()
    try:
        provenance = verify_binary()
        if args.command == 'doctor':
            cfg = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'acloud/config.yaml'
            print(json.dumps({'cli': invoke(['--version']), 'integrity': 'verified',
                              'sdk_dependency': provenance['sdk_dependency'],
                              'config_present': cfg.is_file(),
                              'legacy_config_present': (Path.home() / '.acloud.yaml').is_file(),
                              'environment_variables_present': sorted(
                                  k for k, v in os.environ.items() if k.startswith('ACLOUD_') and v),
                              'live_api_tested': False}, indent=2))
            return 0
        if args.page_size < 1 or args.page_size > 1000 or args.max_pages < 1 or args.timeout < 1:
            parser.error('page size must be 1..1000; max pages and timeout must be positive')
        if any(k not in KINDS for k in args.kinds.split(',')):
            parser.error('supported kinds: ' + ','.join(KINDS))
        if len(set(args.kinds.split(','))) != len(args.kinds.split(',')):
            parser.error('resource kinds must be unique')
        if args.account_label is not None and (not args.account_label.strip() or
                len(args.account_label) > 128 or not args.account_label.isprintable()):
            parser.error('account label must contain 1..128 printable characters')
        if args.project_id is not None and not args.project_id.strip():
            parser.error('project id must not be empty')
        if Path(args.output).exists() or Path(args.output).is_symlink():
            parser.error('output already exists; choose a new path')
        return inventory(args)
    except (CollectionError, OSError, ValueError) as e:
        # Avoid printing exception messages that might include configuration content.
        print(str(e) if isinstance(e, CollectionError) else type(e).__name__, file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
