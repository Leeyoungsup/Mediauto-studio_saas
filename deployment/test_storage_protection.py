import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('source_protection',Path(__file__).parent/'native/github_source.py')
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)

class StorageProtectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.repo=self.root/'application';self.repo.mkdir()
        self.git('init');(self.repo/'backend').mkdir()
    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.repo),*args],stderr=subprocess.DEVNULL).decode()
    def test_windows_link_text_tracked_is_rejected_without_mutation(self):
        path=self.repo/'backend/cell_annotation';path.write_text('C:/old-PC/patches')
        self.git('add','backend/cell_annotation');before=self.git('ls-files','--stage')
        with self.assertRaisesRegex(ValueError,'tracks runtime data'):
            g.protect_runtime_storage({},self.repo)
        self.assertEqual(path.read_text(),'C:/old-PC/patches')
        self.assertEqual(before,self.git('ls-files','--stage'))
    def test_untracked_links_and_directories_are_ignored(self):
        (self.repo/'backend/cell_annotation').symlink_to(self.root/'external',target_is_directory=True)
        (self.repo/'backend/uploads').mkdir();(self.repo/'backend/uploads/slide.ndpi').write_text('keep')
        g.protect_runtime_storage({},self.repo)
        g.protect_runtime_storage({},self.repo)
        self.git('add','.')
        self.assertEqual(self.git('ls-files'),'')
        self.assertTrue((self.repo/'backend/cell_annotation').is_symlink())
        self.assertEqual((self.repo/'backend/uploads/slide.ndpi').read_text(),'keep')
    def test_storage_inside_checkout_rejected_including_symlink(self):
        for target in (self.repo/'patches',):
            with self.assertRaisesRegex(ValueError,'outside the Git checkout'):
                g.protect_runtime_storage({'paths':{'patches':str(target)}},self.repo)
        link=self.root/'alias';link.symlink_to(self.repo,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'outside the Git checkout'):
            g.protect_runtime_storage({'paths':{'patches':str(link/'patches')}},self.repo)
    def test_external_storage_kept(self):
        data=self.root/'storage';data.mkdir();(data/'label.json').write_text('existing')
        g.protect_runtime_storage({'paths':{'patches':str(data)}},self.repo)
        self.assertEqual((data/'label.json').read_text(),'existing')
    def test_host_and_native_share_rules(self):
        self.assertEqual((Path(__file__).parent/'native/github_source.py').read_bytes(),(Path(__file__).parent/'host/github_source.py').read_bytes())
