"""Native API orchestration tests; all HTTP calls are simulated."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import urllib.error
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/lib'))
import native_backups as n


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def archive(self,name='radarr',folder=None):
        folder=folder or self.root/'manual';folder.mkdir(exist_ok=True)
        p=folder/(name+'_backup_new.zip')
        with zipfile.ZipFile(p,'w') as z:
            z.writestr(name+'.db','synthetic database')
            z.writestr('config.yaml' if name=='bazarr' else 'config.xml','synthetic config')
        return p

    def test_yaml_reads_only_intended_sections(self):
        text="auth:\n  apikey: '"+'a'*32+"'\nother:\n  apikey: wrong\ngeneral:\n  port: 6767\n  base_url: ''\n"
        self.assertEqual(n.yaml_scalar(text,'auth','apikey'),'a'*32)
        self.assertEqual(n.yaml_scalar(text,'general','base_url'),'')
        self.assertEqual(n.yaml_scalar(text,'general','port'),'6767')

    def test_yaml_rejects_duplicates_and_aliases(self):
        for text in ('auth:\n  apikey: x\n  apikey: y\n','auth:\n  apikey: *secret\n'):
            with self.assertRaises(RuntimeError):n.yaml_scalar(text,'auth','apikey')

    def test_loopback_only_and_no_key_in_url(self):
        c=n.Client('radarr',7878,'/radarr','a'*32)
        response=Mock();response.read.return_value=b'{}'
        c.opener=Mock();c.opener.open.return_value.__enter__=Mock(return_value=response)
        c.opener.open.return_value.__exit__=Mock(return_value=False)
        c.request('/system/status')
        req=c.opener.open.call_args.args[0]
        self.assertEqual(req.full_url,'http://127.0.0.1:7878/radarr/api/v3/system/status')
        self.assertNotIn('a'*32,req.full_url)
        self.assertEqual(req.get_header('X-api-key'),'a'*32)

    def test_http_errors_do_not_disclose_keys_or_response(self):
        c=n.Client('radarr',7878,'','a'*32);c.opener=Mock()
        c.opener.open.side_effect=urllib.error.HTTPError('url',401,'secret-response',{},io.BytesIO(b'secret-response'))
        with self.assertRaises(RuntimeError) as error:c.request('/system/status')
        self.assertNotIn('secret',str(error.exception));self.assertNotIn('a'*32,str(error.exception))

    def test_redirect_refused(self):
        with self.assertRaises(RuntimeError):n.NoRedirect().redirect_request(None,None,None,None,None,None)

    def test_arr_waits_for_its_command_and_selects_new_zip(self):
        calls=[];counter=[0]
        def api(route,method='GET',body=None):
            calls.append((route,method))
            if route=='/command':return {'id':42}
            if route=='/command/42':
                counter[0]+=1
                if counter[0]==1:return {'id':42,'status':'started'}
                self.archive()
                return {'id':42,'status':'completed'}
            if sum(c[0]=='/system/backup' for c in calls)==1:return [{'id':1}]
            return [{'id':1},{'id':2,'name':'radarr_backup_new.zip','type':'manual'}]
        client=Mock(name='client');client.name='radarr';client.request.side_effect=api
        with patch.object(n.time,'sleep'):
            path,evidence=n.run_arr(client,self.root)
        self.assertEqual(path.name,'radarr_backup_new.zip');self.assertEqual(evidence['command_id'],42)
        self.assertEqual(sum(method=='POST' for _,method in calls),1)

    def test_failed_command_never_reuses_old_zip(self):
        self.archive()
        client=Mock();client.name='radarr'
        client.request.side_effect=[[],{'id':42},{'id':42,'status':'failed'}]
        with self.assertRaises(RuntimeError):n.run_arr(client,self.root)

    def test_completed_command_without_new_zip_fails(self):
        client=Mock();client.name='radarr'
        client.request.side_effect=[[{'id':1}],{'id':42},{'id':42,'status':'completed'},[{'id':1}]]
        with self.assertRaises(RuntimeError):n.run_arr(client,self.root)

    def test_ambiguous_new_results_fail(self):
        client=Mock();client.name='radarr'
        client.request.side_effect=[[],{'id':42},{'id':42,'status':'completed'},[{'id':1,'type':'manual'},{'id':2,'type':'manual'}]]
        with self.assertRaises(RuntimeError):n.run_arr(client,self.root)

    def test_path_traversal_refused(self):
        client=Mock();client.name='radarr'
        client.request.side_effect=[[],{'id':42},{'id':42,'status':'completed'},[{'id':1,'type':'manual','name':'../secret.zip'}]]
        with self.assertRaises(RuntimeError):n.run_arr(client,self.root)

    def test_arr_timeout_sends_only_one_post(self):
        client=Mock();client.name='radarr'
        client.request.side_effect=[[],{'id':42}]
        with patch.object(n,'TIMEOUT',0):
            with self.assertRaises(RuntimeError):n.run_arr(client,self.root)
        self.assertEqual(client.request.call_count,2)

    def test_bazarr_requires_new_stable_valid_zip(self):
        def api(route,method='GET',body=None):
            if method=='POST':
                self.archive('bazarr',self.root)
                return None
            return {'data':[{'job_id':'backup','job_running':False}]}
        client=Mock();client.name='bazarr';client.request.side_effect=api
        with patch.object(n.time,'sleep'):
            path,evidence=n.run_bazarr(client,self.root)
        self.assertTrue(path.exists());self.assertEqual(evidence['task_id'],'backup')
        self.assertEqual(sum(call.args[1:] == ('POST', {'taskid':'backup'}) for call in client.request.call_args_list),1)

    def test_bazarr_timeout_never_accepts_existing_zip(self):
        self.archive('bazarr',self.root)
        client=Mock();client.name='bazarr'
        client.request.return_value={'data':[{'job_id':'backup','job_running':False}]}
        with patch.object(n,'TIMEOUT',0):
            with self.assertRaises(RuntimeError):n.run_bazarr(client,self.root)

    def test_zip_missing_db_rejected(self):
        p=self.root/'backup.zip'
        with zipfile.ZipFile(p,'w') as z:z.writestr('config.yaml','synthetic')
        with self.assertRaises(RuntimeError):n.validate_zip(p,'bazarr')

    def test_generate_freezes_exact_result_without_credentials(self):
        work=self.root/'work';work.mkdir();p=self.archive()
        client=Mock();client.name='radarr'
        with patch.object(n,'check_all',return_value={'radarr':client}),patch.object(n,'run_arr',return_value=(p,{'command_id':42})):
            result=n.generate(work,{'radarr':self.root})
        self.assertEqual(result['radarr'],work/'radarr.zip')
        self.assertTrue((work/'native-api.json').is_file())
        self.assertNotIn('apikey',(work/'native-api.json').read_text().lower())


if __name__=='__main__':unittest.main()
