import importlib.util
import io
import json
import hashlib
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
 def test_existing_git_checkout_keeps_branch_and_local_changes(self):
  import subprocess
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);target=root/'application';runtime=root/'config';runtime.mkdir();target.mkdir()
   def git(*args):return subprocess.run(['git','-C',str(target),*args],check=True,capture_output=True,text=True).stdout.strip()
   git('init','-b','custom');git('config','user.name','Test');git('config','user.email','test@example.invalid')
   (target/'backend').mkdir();file=target/'backend/main.py';file.write_text('original')
   git('add','.');git('commit','-m','initial');git('remote','add','origin','https://github.com/owner/repo.git')
   file.write_text('local edit');(target/'untracked.txt').write_text('keep')
   before=git('status','--porcelain')
   with patch('builtins.input',side_effect=AssertionError('no authentication on reuse')):
    self.assertEqual(g.download({'repository':'owner/repo','ref':'main'},runtime,root),target)
   self.assertEqual(git('branch','--show-current'),'custom');self.assertEqual(git('status','--porcelain'),before)
   self.assertEqual(file.read_text(),'local edit')
 def test_archive_install_is_preserved_and_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'application').mkdir();file=root/'application/custom.py';file.write_text('keep')
   with self.assertRaisesRegex(ValueError,'without .git'):
    g.download({'repository':'owner/repo','ref':'main'},root,root)
   self.assertEqual(file.read_text(),'keep')
 def test_manual_configuration_does_not_register_or_start_a_task(self):
  with patch.object(n,'WINDOWS',True),patch.object(n,'run') as run:
   n.prepare_manual_launch({'project':'mediauto_native_test','bind':'127.0.0.1'},Path('source'))
  command=str(run.call_args_list)
  self.assertIn('Disable-ScheduledTask',command)
  self.assertNotIn('Start-ScheduledTask',command)
  self.assertNotIn('Register-ScheduledTask',command)
 def test_bundled_openslide_is_verified_before_installation(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);vendor=root/'vendor';vendor.mkdir()
   wheel=vendor/'openslide-test.whl';wheel.write_bytes(b'fixture')
   manifest={'filename':wheel.name,'version':'test','sha256':hashlib.sha256(wheel.read_bytes()).hexdigest()}
   (vendor/'openslide-windows.json').write_text(json.dumps(manifest))
   with patch.object(n,'ROOT',root),patch.object(n,'run') as run:
    self.assertEqual(n.install_windows_openslide('python'),'test')
    self.assertIn('--no-index',run.call_args.args[0])
    run.reset_mock();wheel.write_bytes(b'bad')
    with self.assertRaisesRegex(ValueError,'checksum mismatch'):n.install_windows_openslide('python')
    run.assert_not_called()
 def test_native_environment_and_external_links(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);c=self.config(root/'storage');src=root/'application';(src/'backend').mkdir(parents=True)
   (src/'backend/requirements.txt').write_text('openslide-python==1.3.1\npyvips>=2.2,<3\n')
   for key in n.PATHS:Path(c['paths'][key]).mkdir(parents=True)
   calls=[]
   with patch.object(n,'ROOT',root),patch.object(n,'RUNTIME',root/'.runtime'),patch.object(n,'run',side_effect=lambda args,**kw:calls.append(args)),patch.dict('sys.modules',{'conda_setup':types.SimpleNamespace(prepare_main=lambda *args:(root/'envs/mediauto-gpu/bin/python',['conda','run','--prefix',str(root/'envs/mediauto-gpu'),'python']),prepare=lambda *args:{'PHILIPS_PYTHON':'/test/philips/python','PHILIPS_CONDA_ENV':'philips-sdk-py38'},install_sdk=lambda root,config,windows,settings:dict(settings,MEDIAUTO_ENABLE_PHILIPS='1'))}):
    n.prepare_application(c,src)
   app=json.loads((root/'.runtime/app.json').read_text())
   self.assertIn('@127.0.0.1:55440/',app['env']['POSTGRES_URI'])
   self.assertEqual(app['env']['PHILIPS_PYTHON'],'/test/philips/python')
   self.assertEqual((src/'backend/cell_annotation').resolve(),Path(c['paths']['patches']))
   self.assertEqual((src/'backend/.secrets.json').resolve(),Path(c['paths']['secrets'])/'.secrets.json')
   self.assertFalse(any('docker' in str(x).lower() for x in calls))

if __name__=='__main__':unittest.main()
