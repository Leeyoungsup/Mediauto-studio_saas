import importlib.util
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

ROOT=Path(__file__).parent/'native'
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
n=load('native_install',ROOT/'install.py');g=load('github_source',ROOT/'github_source.py')

class NativeTests(unittest.TestCase):
 def config(self,root):
  return {'project':'mediauto_native_test','repository':'owner/repo','ref':'main','admin_id':'admin','admin_password':'a'*24+'Aa!',
          'app_port':18095,'db_port':55440,'bind':'127.0.0.1','db_password':'b'*48,'pg_password':'c'*48,
          'paths':{k:str(root/k) for k in (*n.PATHS,'database')}}
 def test_settings_contain_no_github_secret(self):
  with tempfile.TemporaryDirectory() as d:
   c=self.config(Path(d));n.validate(c)
   self.assertNotIn('token',json.dumps(c))
 def test_archive_traversal_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   z=Path(d)/'x.zip'
   with zipfile.ZipFile(z,'w') as f:f.writestr('repo/../../outside.py','bad')
   with self.assertRaises(ValueError):g.extract(z,Path(d)/'app')
   self.assertFalse((Path(d)/'outside.py').exists())
 def test_authorization_is_only_sent_to_api(self):
  captured=[]
  class Opener:
   def open(self,req,timeout):captured.append(req);return 'ok'
  with patch.object(g.urllib.request,'build_opener',return_value=Opener()):
   self.assertEqual(g.api('/repos/o/r','Basic secret'),'ok')
  self.assertEqual(captured[0].host,'api.github.com')
  self.assertEqual(captured[0].get_header('Authorization'),'Basic secret')
  self.assertIsNone(g.NoRedirect().redirect_request(captured[0],None,302,'',{},'https://other.example'))
 def test_redirect_download_has_no_auth_and_token_not_saved(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);runtime=root/'.runtime';runtime.mkdir();commit='a'*40
   blob=io.BytesIO()
   with zipfile.ZipFile(blob,'w') as z:z.writestr('repo-'+commit+'/backend/main.py','pass')
   calls=[]
   def fake_api(path,auth):
    calls.append(auth)
    if '/commits/' in path:return io.BytesIO(json.dumps({'sha':commit}).encode())
    raise urllib.error.HTTPError('https://api.github.com',302,'redirect',{'Location':'https://codeload.github.com/repo/zip/commit'},None)
   class Opener:
    def open(self,url,timeout):
     self_url=url
     assert isinstance(self_url,str) # No request carrying an Authorization header.
     return io.BytesIO(blob.getvalue())
   with patch('builtins.input',return_value='alice'),patch.object(g.sys.stdin,'isatty',return_value=True),patch.object(g.getpass,'getpass',return_value='secret-PAT'),patch.object(g,'api',side_effect=fake_api),patch.object(g.urllib.request,'build_opener',return_value=Opener()):
    target=g.download({'repository':'owner/repo','ref':'main'},runtime,root)
   self.assertTrue((target/'backend/main.py').exists())
   self.assertEqual(len(calls),2)
   for p in root.rglob('*'):
    if p.is_file():self.assertNotIn('secret-PAT',p.read_text())
   self.assertFalse((runtime/'source-download.zip').exists())
 def test_native_environment_and_external_links(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);c=self.config(root/'storage');src=root/'application';(src/'backend').mkdir(parents=True)
   (src/'backend/requirements.txt').write_text('openslide-python==1.3.1\npyvips>=2.2,<3\n')
   for key in n.PATHS:Path(c['paths'][key]).mkdir(parents=True)
   calls=[]
   with patch.object(n,'ROOT',root),patch.object(n,'RUNTIME',root/'.runtime'),patch.object(n,'run',side_effect=lambda args,**kw:calls.append(args)),patch.dict('sys.modules',{'conda_setup':types.SimpleNamespace(prepare=lambda *args:{'PHILIPS_PYTHON':'/test/philips/python','PHILIPS_CONDA_ENV':'philips-sdk-py38'},install_sdk=lambda root,config,windows,settings:dict(settings,MEDIAUTO_ENABLE_PHILIPS='1'))}):
    n.prepare_application(c,src)
   app=json.loads((root/'.runtime/app.json').read_text())
   self.assertIn('@127.0.0.1:55440/',app['env']['POSTGRES_URI'])
   self.assertEqual(app['env']['PHILIPS_PYTHON'],'/test/philips/python')
   self.assertEqual((src/'backend/cell_annotation').resolve(),Path(c['paths']['patches']))
   self.assertEqual((src/'backend/.secrets.json').resolve(),Path(c['paths']['secrets'])/'.secrets.json')
   self.assertFalse(any('docker' in str(x).lower() for x in calls))

if __name__=='__main__':unittest.main()
