import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs

ROOT=Path(__file__).resolve().parents[1]
sys_path = str(ROOT/'scripts')
import sys
sys.path.insert(0, sys_path)
from unittest import mock
import tarfile
import install_cli
HELPER=ROOT/'scripts/inventory.py'
spec=importlib.util.spec_from_file_location('inventory',HELPER)
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.mode='normal'; self.requests=[]
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def reply(self,obj,status=200):
                self.send_response(status); self.send_header('Content-Type','application/json'); self.end_headers()
                self.wfile.write(json.dumps(obj).encode())
            def do_POST(self):
                owner.requests.append(('POST',self.path))
                if self.path!='/token': return self.reply({},405)
                self.reply({'access_token':'fake-local-test-token','token_type':'Bearer','expires_in':3600})
            def do_GET(self):
                owner.requests.append(('GET',self.path))
                p=urlparse(self.path); q=parse_qs(p.query); offset=int(q.get('offset',['0'])[0])
                if p.path=='/projects':
                    values=[{'metadata':{'id':'project-a','name':'Alpha'}},{'metadata':{'id':'project-b','name':'Beta'}}]
                elif p.path.endswith('/cloudServers'):
                    if owner.mode=='denied': return self.reply({'message':'NEVER-ECHO-THIS-SECRET'},403)
                    if owner.mode=='malformed': return self.reply({'values':[{}],'total':1})
                    values=[] if owner.mode in ('empty','all-empty') else [
                        {'metadata':{'id':'server-1','name':'One'},'properties':{'status':{'state':'Stopped'}}},
                        {'metadata':{'id':'server-2','name':'Two'},'properties':{'status':{'state':'Running'}}}]
                elif owner.mode=='all-empty' and p.path.startswith('/projects/'):
                    values=[]
                else: return self.reply({'message':p.path},404)
                if owner.mode=='repeat': offset=0
                batch=values[offset:offset+1]
                self.reply({'values':batch,'total':len(values),'next':''})
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        url=f'http://127.0.0.1:{self.server.server_port}'
        self.env={k:v for k,v in os.environ.items() if not k.startswith('ACLOUD_')}
        self.env.update(ACLOUD_CLIENT_ID='fake-local-id',ACLOUD_CLIENT_SECRET='fake-local-secret',
                        ACLOUD_BASE_URL=url,ACLOUD_TOKEN_ISSUER_URL=url+'/token',XDG_CONFIG_HOME=self.tmp.name)
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.tmp.cleanup()
    def run_inventory(self,extra=()):
        out=Path(self.tmp.name)/'inventory.json'
        r=subprocess.run(['python3',str(HELPER),'inventory','--kinds','servers','--page-size','1',
                          '--output',str(out),*extra],env=self.env,capture_output=True,text=True)
        self.assertTrue(out.exists(),r.stderr+r.stdout)
        return r,json.loads(out.read_text()),out
    def test_pagination_real_official_cli(self):
        r,d,out=self.run_inventory()
        self.assertEqual(r.returncode,0,r.stderr+d.__repr__())
        self.assertTrue(d['complete']);self.assertEqual(len(d['projects']),2)
        self.assertEqual(d['projects'][0]['resources']['servers']['count'],2)
        self.assertEqual(out.stat().st_mode & 0o777,0o600)
        self.assertTrue(any('offset=1' in p for m,p in self.requests if m=='GET'))
        self.assertTrue(all(m=='GET' or p=='/token' for m,p in self.requests))
    def test_empty_lists_real_cli(self):
        self.mode='empty';r,d,_=self.run_inventory(['--project-id','project-a'])
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(d['projects'][0]['resources']['servers']['count'],0)
    def test_labeled_scope_is_recorded_without_endpoint_values(self):
        r,d,_=self.run_inventory(['--project-id','project-a','--account-label','example-account'])
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(d['schema_version'],2)
        self.assertEqual(d['scope']['account_label'],'example-account')
        self.assertEqual(d['scope']['project_id'],'project-a')
        self.assertEqual(len(d['scope']['endpoint_fingerprint']),64)
        self.assertNotIn(self.env['ACLOUD_BASE_URL'],json.dumps(d))
    def test_invalid_scope_flags_fail_before_any_api_call(self):
        out=Path(self.tmp.name)/'duplicate.json'
        for flags in (['--kinds','servers,servers'], ['--project-id',''],
                      ['--account-label',' '], ['--account-label','bad\nlabel'],
                      ['--account-label','a'*129]):
            with self.subTest(flags=flags):
                r=subprocess.run(['python3',str(HELPER),'inventory',*flags,
                                  '--output',str(out)],env=self.env,capture_output=True,text=True)
                self.assertEqual(r.returncode,2)
                self.assertFalse(out.exists());self.assertEqual(self.requests,[])
    def test_permission_error_is_not_zero_and_no_body_leak(self):
        self.mode='denied';r,d,_=self.run_inventory(['--project-id','project-a'])
        self.assertEqual(r.returncode,2);self.assertFalse(d['complete'])
        self.assertEqual(d['errors'][0]['code'],'http_403')
        self.assertIsNone(d['projects'][0]['resources']['servers']['count'])
        self.assertNotIn('NEVER-ECHO',json.dumps(d)+r.stdout+r.stderr)
    def test_repeated_page_fails_closed(self):
        self.mode='repeat';r,d,_=self.run_inventory(['--project-id','project-a'])
        self.assertEqual(r.returncode,2);self.assertEqual(d['errors'][0]['code'],'duplicate_or_repeated_page')
    def test_all_seven_resource_families_empty(self):
        self.mode='all-empty'
        r,d,_=self.run_inventory(['--project-id','project-a','--kinds',','.join(mod.KINDS)])
        self.assertEqual(r.returncode,0,json.dumps(d))
        self.assertEqual(len(d['projects'][0]['resources']),7)
        self.assertTrue(all(v['count']==0 for v in d['projects'][0]['resources'].values()))
    def test_output_not_overwritten(self):
        out=Path(self.tmp.name)/'existing.json';out.write_text('keep')
        r=subprocess.run(['python3',str(HELPER),'inventory','--output',str(out)],env=self.env,capture_output=True)
        self.assertNotEqual(r.returncode,0);self.assertEqual(out.read_text(),'keep');self.assertEqual(self.requests,[])

class InstallerTests(unittest.TestCase):
    def test_corrupt_download_does_not_touch_installed_files(self):
        before=(ROOT/'bin/acloud').read_bytes()
        with mock.patch.object(install_cli.urllib.request,'urlopen',return_value=io.BytesIO(b'corrupt')):
            with self.assertRaisesRegex(ValueError,'SHA-256 mismatch'):
                install_cli.main()
        self.assertEqual((ROOT/'bin/acloud').read_bytes(),before)
    def test_archive_paths_are_never_extracted(self):
        stream=io.BytesIO()
        with tarfile.open(fileobj=stream,mode='w:gz') as archive:
            item=tarfile.TarInfo('../../acloud');item.size=4
            archive.addfile(item,io.BytesIO(b'test'))
        self.assertEqual(install_cli.extract_binary(stream.getvalue()),b'test')
    def test_symlink_archive_member_is_rejected(self):
        stream=io.BytesIO()
        with tarfile.open(fileobj=stream,mode='w:gz') as archive:
            item=tarfile.TarInfo('acloud');item.type=tarfile.SYMTYPE;item.linkname='/etc/passwd'
            archive.addfile(item)
        with self.assertRaisesRegex(ValueError,'Unexpected release archive'):
            install_cli.extract_binary(stream.getvalue())

if __name__=='__main__':unittest.main(verbosity=2)
