from pathlib import Path
import os
import subprocess
import tempfile
import unittest

class LinuxDriverTests(unittest.TestCase):
    def simulate(self,installed,candidate):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);bin=root/'bin';bin.mkdir();pci=root/'pci/device';pci.mkdir(parents=True)
            (pci/'vendor').write_text('0x10de');(pci/'class').write_text('0x030000')
            (root/'os-release').write_text('ID=ubuntu\n');(root/'kernel').write_text('Linux')
            commands={'nvidia-smi':f'echo {installed}', 'apt-get':f'echo "$*" >> "{root}/calls"',
                      'ubuntu-drivers':'echo "driver : nvidia-driver-580 - distro non-free recommended"',
                      'apt-cache':f'echo "Candidate: {candidate}"'}
            for name,body in commands.items():
                p=bin/name;p.write_text('#!/bin/bash\n'+body+'\n');p.chmod(0o755)
            s=(Path(__file__).parent/'native/setup-nvidia-driver.sh').read_text()
            s=s.replace('if [[ $EUID -ne 0 ]]; then exec sudo bash "$0" "$@"; fi','')
            s=s.replace('/sys/bus/pci/devices/*',str(root/'pci/*')).replace('/etc/os-release',str(root/'os-release')).replace('/proc/sys/kernel/osrelease',str(root/'kernel'))
            p=root/'test.sh';p.write_text(s)
            result=subprocess.run(['bash',str(p)],env=dict(os.environ,PATH=str(bin)+':'+os.environ['PATH']),capture_output=True,text=True)
            calls=(root/'calls').read_text() if (root/'calls').exists() else ''
            return result,calls
    def test_compatible_driver_does_not_install(self):
        result,calls=self.simulate('580.10','580.10')
        self.assertEqual(result.returncode,0);self.assertEqual(calls,'')
    def test_old_driver_install_requires_manual_reboot(self):
        result,calls=self.simulate('470.10','580.10')
        self.assertEqual(result.returncode,20);self.assertIn('REBOOT REQUIRED',result.stdout)
        self.assertIn('nvidia-driver-580',calls)
    def test_old_candidate_epoch_does_not_bypass_minimum(self):
        result,calls=self.simulate('470.10','3:535.100')
        self.assertEqual(result.returncode,1);self.assertNotIn('install -y linux-headers',calls)
