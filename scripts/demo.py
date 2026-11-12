#!/usr/bin/env python3
"""Run the real inventory helper against synthetic localhost data; no Aruba account."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import reports
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = [
    {'metadata': {'id': 'demo-production', 'name': 'Production (demo)'}},
    {'metadata': {'id': 'demo-staging', 'name': 'Staging (demo)'}},
]
FAMILIES = {
    'cloudServers': ('servers', 'Servers'),
    'blockStorages': ('volumes', 'Volumes'),
    'vpcs': ('vpcs', 'VPCs'),
    'elasticIps': ('ips', 'Elastic IPs'),
    'dbaas': ('dbaas', 'Databases'),
    'kaas': ('kaas', 'Kubernetes'),
    'registries': ('registries', 'Registries'),
}
COUNTS = {
    'demo-production': (3, 4, 1, 2, 1, 1, 1),
    'demo-staging': (1, 1, 1, 1, 0, 0, 0),
}


class DemoHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, body, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_POST(self):
        if self.path != '/token':
            return self.reply({}, 405)
        self.reply({'access_token': 'synthetic-local-demo-token',
                    'token_type': 'Bearer', 'expires_in': 3600})

    def do_GET(self):
        parsed = urlparse(self.path)
        parts = parsed.path.strip('/').split('/')
        if parts == ['projects']:
            values = PROJECTS
        elif (len(parts) == 5 and parts[0] == 'projects' and parts[2] == 'providers'
              and parts[1] in COUNTS and parts[4] in FAMILIES):
            index = list(FAMILIES).index(parts[4])
            kind = FAMILIES[parts[4]][0]
            count = COUNTS[parts[1]][index]
            if self.server.phase == 'after' and parts[1] == 'demo-production':
                count += 1 if kind == 'servers' else -1 if kind == 'volumes' else 0
            values = [
                {'metadata': {'id': f'{parts[1]}-{kind}-{n + 1}',
                              'name': f'demo-{kind}-{n + 1}'}}
                for n in range(count)
            ]
            if self.server.phase == 'after' and parts[1] == 'demo-production' and kind == 'servers':
                values[0]['metadata']['name'] = 'demo-servers-1-renamed'
        else:
            return self.reply({}, 404)
        query = parse_qs(parsed.query)
        offset = int(query.get('offset', ['0'])[0])
        limit = int(query.get('limit', ['50'])[0])
        self.reply({'values': values[offset:offset + limit], 'total': len(values), 'next': ''})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', help='Retain synthetic JSON/Markdown in a NEW private directory')
    args = parser.parse_args()
    if args.output_dir and (Path(args.output_dir).exists() or Path(args.output_dir).is_symlink()):
        parser.error('output directory already exists; choose a new path')
    print('ARUBA CLOUD / LOCAL DEMO', flush=True)
    print('Synthetic data. Official CLI. No Aruba account or cloud API calls.\n', flush=True)
    if not (ROOT / 'bin' / 'acloud').is_file():
        print('Install the pinned CLI first: python3 scripts/install_cli.py', file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix='aruba-cloud-demo-') as folder:
        server = ThreadingHTTPServer(('127.0.0.1', 0), DemoHandler)
        server.phase = 'before'
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f'http://127.0.0.1:{server.server_port}'
            env = {k: v for k, v in os.environ.items() if not k.startswith('ACLOUD_')}
            env.update(ACLOUD_CLIENT_ID='synthetic-demo-id',
                       ACLOUD_CLIENT_SECRET='synthetic-demo-secret',
                       ACLOUD_BASE_URL=url, ACLOUD_TOKEN_ISSUER_URL=url + '/token',
                       XDG_CONFIG_HOME=folder,
                       NO_PROXY='127.0.0.1,localhost', no_proxy='127.0.0.1,localhost')
            for phase in ('before', 'after'):
                server.phase = phase
                output = Path(folder) / f'{phase}.json'
                run = subprocess.run(
                    [sys.executable, str(ROOT / 'scripts' / 'inventory.py'), 'inventory',
                     '--account-label', 'synthetic-demo', '--page-size', '2', '--output', str(output)],
                    env=env, capture_output=True, text=True, timeout=60,
                )
                if run.returncode or not output.is_file():
                    print('Local demo failed. Run the fixture tests for diagnostics.', file=sys.stderr)
                    return 2
            report = reports.read_inventory(Path(folder) / 'before.json')
            if not report['complete'] or len(report['projects']) != len(PROJECTS):
                print('Local demo returned an incomplete inventory.', file=sys.stderr)
                return 2
            labels = [value[1] for value in FAMILIES.values()]
            print(f'{"Project":<24}' + ''.join(f'{label:>12}' for label in labels))
            print('-' * (24 + 12 * len(labels)))
            totals = [0] * len(labels)
            for entry in report['projects']:
                name = entry['project']['metadata']['name']
                counts = [entry['resources'][kind]['count'] for kind, _ in FAMILIES.values()]
                print(f'{name:<24}' + ''.join(f'{count:>12}' for count in counts))
                totals = [a + b for a, b in zip(totals, counts)]
            print(f'\nComplete: yes | Projects: {len(report["projects"])} | Resources: {sum(totals)} | Errors: 0')
            for command in (
                ['render', str(Path(folder) / 'before.json'), '--output', str(Path(folder) / 'report.md')],
                ['diff', str(Path(folder) / 'before.json'), str(Path(folder) / 'after.json'),
                 '--output', str(Path(folder) / 'changes.md')],
            ):
                run = subprocess.run([sys.executable, str(ROOT / 'scripts/reports.py'), *command],
                                     env=env, capture_output=True, text=True, timeout=10)
                if run.returncode:
                    print('Local report demonstration failed.', file=sys.stderr)
                    return 2
            changes = (Path(folder) / 'changes.md').read_text(encoding='utf-8')
            if not all(f'**{action}:** 1' in changes for action in ('Added', 'Removed', 'Modified')):
                print('Unexpected local comparison result.', file=sys.stderr)
                return 2
            print('Second scan: 1 added, 1 removed, 1 modified resource. No uncomparable scopes.')
            print('Markdown inventory and change reports generated offline with private permissions.')
            if args.output_dir:
                destination = Path(args.output_dir)
                destination.mkdir(mode=0o700)
                for name in ('before.json', 'after.json', 'report.md', 'changes.md'):
                    reports.write_private(destination / name, (Path(folder) / name).read_text(encoding='utf-8'))
                print(f'Synthetic example files retained in: {destination.resolve()}')
            else:
                print('Temporary demo files removed on exit. Use --output-dir NEW_DIRECTORY to retain them.')
            print('This verifies the local workflow, not live Aruba access or compatibility.')
            return 0
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        sys.exit('Local demo failed; no cloud operations were requested.')
