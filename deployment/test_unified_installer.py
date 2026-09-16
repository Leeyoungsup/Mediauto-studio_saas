import importlib.util
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent

def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

class UnifiedTests(unittest.TestCase):
 def test_linux_selector_routes_both_modes_and_defaults_to_docker(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'install.sh').write_bytes((ROOT/'installer/install.sh').read_bytes())
   for name in ('docker','native'):
    (root/name).mkdir();(root/name/'install.sh').write_text('echo selected-'+name+'\n')
   for choice,expected in [('\n','docker'),('1\n','docker'),('2\n','native')]:
    result=subprocess.run(['bash',root/'install.sh'],input=choice,text=True,capture_output=True)
    self.assertEqual(result.returncode,0);self.assertIn('selected-'+expected,result.stdout)
   self.assertNotEqual(subprocess.run(['bash',root/'install.sh'],input='3\n',text=True,capture_output=True).returncode,0)
 def test_repository_repair_preserves_canonical_sources_and_is_repeatable(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);apt=root/'apt/sources.list.d';apt.mkdir(parents=True)
   nvidia='deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://nvidia.github.io/libnvidia-container/stable/deb/$(ARCH) /\n'
   (apt/'nvidia-container-toolkit.list').write_text(nvidia)
   (apt/'mediauto-nvidia.list').write_text(nvidia.replace('nvidia-container-toolkit-keyring','mediauto-nvidia'))
   docker='deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu jammy stable\n'
   (apt/'docker.list').write_text(docker)
   legacy=apt/'archive_uri-https_download_docker_com_linux_ubuntu-jammy.list';legacy.write_text('deb [arch=amd64] https://download.docker.com/linux/ubuntu jammy stable\n')
   osrelease=root/'os-release';osrelease.write_text('ID=ubuntu\n')
   script=(ROOT/'installer/setup-nvidia-runtime.sh').read_text().replace('if [[ $EUID -ne 0 ]]; then exec sudo bash "$0" "$@"; fi','').replace('/etc/apt',str(root/'apt')).replace('/etc/os-release',str(osrelease))
   path=root/'repair.sh';path.write_text(script)
   for _ in range(2):subprocess.run(['bash',path,'--prepare-repositories'],check=True,capture_output=True)
   self.assertEqual((apt/'docker.list').read_text(),docker)
   self.assertEqual((apt/'nvidia-container-toolkit.list').read_text(),nvidia)
   self.assertFalse((apt/'mediauto-nvidia.list').exists());self.assertFalse(legacy.exists())
   self.assertEqual(len(list(apt.glob('*.disabled-*'))),2)
 def test_gpu_checks_refuse_cpu_in_both_modes(self):
  fake_torch=types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda:False))
  with patch.dict('sys.modules',{'torch':fake_torch,'torchvision':types.SimpleNamespace()}):
   for file in ('host/container_runner.py','native/gpu_check.py'):
    mod=load('gpu_gate',ROOT/file)
    with self.assertRaisesRegex(RuntimeError,'CPU fallback is disabled'):mod.check_gpu()

if __name__=='__main__':unittest.main()
