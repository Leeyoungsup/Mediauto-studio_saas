import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).parent
spec=importlib.util.spec_from_file_location('conda_setup',ROOT/'native/conda_setup.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)

class CondaSetupTests(unittest.TestCase):
    def test_main_gpu_environment_is_conda_and_reused(self):
        for windows in (True,False):
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                with patch.object(c,'find_conda',return_value=root/'conda'),patch.object(c,'invoke') as invoke:
                    python,command=c.prepare_main(root,{'paths':{'cache':str(root/'cache')}},windows)
                    self.assertIn('create',invoke.call_args_list[0].args[0])
                    self.assertIn('python=3.12',invoke.call_args_list[0].args[0])
                    self.assertIn('run',command)
                    self.assertIn('medicus-saas',str(python))
                    python.parent.mkdir(parents=True);python.touch();invoke.reset_mock()
                    c.prepare_main(root,{'paths':{'cache':str(root/'cache')}},windows)
                    self.assertEqual(invoke.call_count,1 if windows else 2)
                    self.assertIn('run',invoke.call_args.args[0])

    def test_old_linux_cpp_runtime_is_repaired_and_rechecked(self):
        for repair_works in (True, False):
            with self.subTest(repair_works=repair_works), tempfile.TemporaryDirectory() as directory:
                root=Path(directory);python=root/'envs/medicus-saas/bin/python'
                python.parent.mkdir(parents=True);python.touch()
                calls=[]
                def invoke(args, **kwargs):
                    calls.append(args)
                    if len(calls)==1 or (len(calls)==3 and not repair_works):
                        raise subprocess.CalledProcessError(1,args)
                with patch.object(c,'find_conda',return_value=root/'conda'),patch.object(c,'invoke',side_effect=invoke):
                    if repair_works:
                        c.prepare_main(root,{'paths':{'cache':str(root/'cache')}},False)
                    else:
                        with self.assertRaises(subprocess.CalledProcessError):
                            c.prepare_main(root,{'paths':{'cache':str(root/'cache')}},False)
                self.assertIn('libstdcxx-ng>=14',calls[1])
                self.assertIn('libgcc-ng>=14',calls[1])
                self.assertEqual(calls[0],calls[2])
                self.assertEqual(len(calls),4 if repair_works else 3)

    def test_windows_broken_pillow_repaired_through_conda_and_rechecked(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);python=root/'envs/philips-sdk-py37/python.exe'
            python.parent.mkdir(parents=True);python.touch()
            calls=[]
            def invoke(args, **kwargs):
                calls.append(args)
                if len(calls)==1: raise subprocess.CalledProcessError(1,args)
            with patch.object(c,'find_conda',return_value=root/'conda'),patch.object(c,'invoke',side_effect=invoke):
                c.prepare(root,{'paths':{'cache':str(root/'cache')}},True)
            self.assertEqual(len(calls),4)
            self.assertIn('Pillow==9.5.0',calls[1])
            self.assertIn('--only-binary=:all:',calls[1])
            self.assertIn('--no-deps',calls[1])
            self.assertEqual(calls[0],calls[2])
            self.assertTrue(all('run' in args and '--name' in args for args in calls))

    def test_failed_pillow_repair_stops_environment_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);python=root/'envs/philips-sdk-py37/python.exe'
            python.parent.mkdir(parents=True);python.touch()
            with patch.object(c,'find_conda',return_value=root/'conda'),patch.object(c,'invoke',side_effect=subprocess.CalledProcessError(1,['fixture'])) as invoke:
                with self.assertRaises(subprocess.CalledProcessError):
                    c.prepare(root,{'paths':{'cache':str(root/'cache')}},True)
            self.assertEqual(invoke.call_count,2)

    def setUp(self):
        lookup=patch.object(c,'named_prefix',side_effect=lambda conda,name:Path(conda).parent/'envs'/name)
        lookup.start();self.addCleanup(lookup.stop)
        shell=patch.object(c,'initialize_shell');shell.start();self.addCleanup(shell.stop)
        compatibility=patch.object(c,'ensure_linux_compatibility')
        compatibility.start();self.addCleanup(compatibility.stop)

    def test_platform_environment_selection_and_reuse(self):
        for windows,minor in [(True,7),(False,8)]:
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);config={'paths':{'cache':str(root/'cache')}}
                with patch.object(c,'find_conda',return_value=root/'conda'),patch.object(c,'invoke') as invoke:
                    result=c.prepare(root,config,windows)
                    create=invoke.call_args_list[0]
                    self.assertIn('python=3.'+str(minor),create.args[0])
                    self.assertIn('--override-channels',create.args[0])
                    self.assertEqual(create.kwargs['env']['CONDA_PKGS_DIRS'],str(root/'cache/conda/pkgs'))
                    self.assertEqual(result['PHILIPS_CONDA_ENV'],'philips-sdk-py3'+str(minor))
                    python=Path(result['PHILIPS_PYTHON']);python.parent.mkdir(parents=True);python.touch()
                    invoke.reset_mock();c.prepare(root,config,windows)
                    self.assertEqual(invoke.call_count,2 if windows else 1)
                    self.assertIn('run',invoke.call_args.args[0])

    def test_missing_conda_uses_verified_installer_on_each_platform(self):
        for windows in (True,False):
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);config={'paths':{'cache':str(root/'cache')}}
                expected=c.INSTALLERS['windows' if windows else 'linux'][1]
                def download(url,destination):
                    self.assertTrue(url.startswith('https://repo.anaconda.com/miniconda/Miniconda3-'))
                    Path(destination).write_bytes(b'fixture')
                with patch.object(c,'find_conda',side_effect=[None,root/'conda']),patch.object(c.urllib.request,'urlretrieve',side_effect=download),patch.object(c,'digest',return_value=expected),patch.object(c,'invoke') as invoke:
                    c.prepare(root,config,windows)
                    args=invoke.call_args_list[0].args[0]
                    if windows:
                        self.assertIn('/RegisterPython=0',args);self.assertTrue(args[-1].startswith('/D='))
                    else:self.assertEqual(args[0],'bash');self.assertIn('-b',args)

    def test_bad_download_never_executes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def download(url,destination):Path(destination).write_bytes(b'bad')
            with patch.object(c,'find_conda',return_value=None),patch.object(c.urllib.request,'urlretrieve',side_effect=download),patch.object(c,'invoke') as invoke:
                with self.assertRaisesRegex(RuntimeError,'checksum mismatch'):
                    c.prepare(root,{'paths':{'cache':str(root/'cache')}},False)
                invoke.assert_not_called()

    def test_bundled_sdk_install_checks_license_hash_and_smoke_test(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'native';root.mkdir()
            bundle=root.parent/'Philips_SDK';(bundle/'sdk').mkdir(parents=True)
            license=bundle/'sdk/EULA Research.license.txt';license.write_text('SDK license fixture')
            manifest={'platform':'linux','sdk_directory':'sdk','files':[{'path':'sdk/EULA Research.license.txt','sha256':c.digest(license)}]}
            (bundle/'manifest.json').write_text(json.dumps(manifest))
            config={'data_root':str(root.parent/'data'),'paths':{'cache':str(root.parent/'cache'),'temp':str(root.parent/'temp')}}
            settings={'PHILIPS_CONDA_ENV':'philips-sdk-py38','PHILIPS_PYTHON':str(root/'envs/philips-sdk-py38/bin/python')}
            with patch.object(c,'find_conda',return_value=root/'conda'),patch.object(c,'invoke') as invoke,patch('builtins.input',return_value='yes') as answer:
                result=c.install_sdk(root,config,False,settings)
                self.assertEqual(result['MEDIAUTO_ENABLE_PHILIPS'],'1')
                self.assertIn('--sdk-source',invoke.call_args_list[0].args[0])
                self.assertIn('--check-only',invoke.call_args_list[1].args[0])
                self.assertEqual(answer.call_count,1)
                invoke.reset_mock();answer.reset_mock()
                c.install_sdk(root,config,False,settings)
                self.assertEqual(invoke.call_count,1);answer.assert_not_called()
                license.write_text('tampered')
                invoke.reset_mock()
                with self.assertRaisesRegex(RuntimeError,'checksum mismatch'):c.install_sdk(root,config,False,settings)
                invoke.assert_not_called()

class NamedResolutionTests(unittest.TestCase):
    def test_only_conda_search_directories_are_used(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);first=root/'first';second=root/'second'
            prefix=second/'medicus-saas';(prefix/'conda-meta').mkdir(parents=True)
            (prefix/'conda-meta/history').touch()
            response=subprocess.CompletedProcess([],0,stdout=json.dumps({'envs_dirs':[str(first),str(second)]}))
            with patch.object(c,'invoke',return_value=response):
                self.assertEqual(c.named_prefix('conda','medicus-saas'),prefix)
                self.assertEqual(c.named_prefix('conda','philips-sdk-py37'),first/'philips-sdk-py37')

if __name__=='__main__':unittest.main()
