#!/usr/bin/env python3
"""Run the real inventory helper against synthetic localhost data; no Aruba account."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
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
            values = [
                {'metadata': {'id': f'{parts[1]}-{kind}-{n + 1}',
                              'name': f'demo-{kind}-{n + 1}'}}
                for n in range(COUNTS[parts[1]][index])
            ]
        else:
            return self.reply({}, 404)
        query = parse_qs(parsed.query)
        offset = int(query.get('offset', ['0'])[0])
        limit = int(query.get('limit', ['50'])[0])
        self.reply({'values': values[offset:offset + limit], 'total': len(values), 'next': ''})


def main():
    print('ARUBA CLOUD / LOCAL DEMO', flush=True)
    print('Synthetic data. Official CLI. No Aruba account or cloud API calls.\n', flush=True)
    if not (ROOT / 'bin' / 'acloud').is_file():
        print('Install the pinned CLI first: python3 scripts/install_cli.py', file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix='aruba-cloud-demo-') as folder:
        server = ThreadingHTTPServer(('127.0.0.1', 0), DemoHandler)
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
            output = Path(folder) / 'demo.json'
            run = subprocess.run(
                [sys.executable, str(ROOT / 'scripts' / 'inventory.py'), 'inventory',
                 '--page-size', '2', '--output', str(output)],
                env=env, capture_output=True, text=True, timeout=60,
            )
            if run.returncode or not output.is_file():
                print('Local demo failed. Run the fixture tests for diagnostics.', file=sys.stderr)
                return 2
            report = json.loads(output.read_text())
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
            print('Report created with private permissions; temporary demo files removed on exit.')
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
