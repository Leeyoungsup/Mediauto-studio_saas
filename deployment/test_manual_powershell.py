"""Exercise PowerShell exit behavior, including an absent scheduled task."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('manual_install',Path(__file__).parent/'native/install.py')
n=importlib.util.module_from_spec(spec);spec.loader.exec_module(n)
PWSH=shutil.which('pwsh') or ('/tmp/mediauto-pwsh/pwsh' if Path('/tmp/mediauto-pwsh/pwsh').is_file() else None)

@unittest.skipUnless(PWSH,'PowerShell required')
class ManualPowerShellTests(unittest.TestCase):
 def commands(self):
  with patch.object(n,'WINDOWS',True),patch.object(n,'run') as run:
   n.prepare_manual_launch({'project':'mediauto_test','bind':'0.0.0.0','app_port':18093},Path('source'))
  return [call.args[0][-1] for call in run.call_args_list]
 def execute(self,stub,command):
  return subprocess.run([PWSH,'-NoProfile','-Command',stub+'; '+command],capture_output=True,text=True)
 def test_no_task_is_success(self):
  result=self.execute('function Get-ScheduledTask { [CmdletBinding()]param() }',self.commands()[0])
  self.assertEqual(result.returncode,0,result.stderr)
 def test_real_query_error_is_not_hidden(self):
  result=self.execute("function Get-ScheduledTask { [CmdletBinding()]param(); throw 'access denied fixture' }",self.commands()[0])
  self.assertEqual(result.returncode,1)
  self.assertIn('App task configuration failed',result.stderr)
  self.assertIn('access denied fixture',result.stderr)
 def test_missing_firewall_rule_can_be_created(self):
  stub="function Get-NetFirewallRule { [CmdletBinding()]param() }; function Remove-NetFirewallRule { [CmdletBinding()]param() }; function New-NetFirewallRule { [CmdletBinding()]param($Name,$DisplayName,$Direction,$Action,$Protocol,$LocalPort,$RemoteAddress); Write-Output created }"
  result=self.execute(stub,self.commands()[1])
  self.assertEqual(result.returncode,0,result.stderr)
 def test_firewall_error_is_not_hidden(self):
  stub="function Get-NetFirewallRule { [CmdletBinding()]param(); throw 'firewall failure fixture' }"
  result=self.execute(stub,self.commands()[1])
  self.assertEqual(result.returncode,1)
  self.assertIn('Web firewall configuration failed',result.stderr)

if __name__=='__main__':unittest.main()
