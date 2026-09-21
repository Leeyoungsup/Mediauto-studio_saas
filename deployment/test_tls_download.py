import ast
import os
from pathlib import Path
import ssl
import subprocess
import types
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch

class TLSDownloadTests(unittest.TestCase):
    def functions(self):
        for name in ('native/install.py','host/install.py','native/conda_setup.py'):
            tree=ast.parse((Path(__file__).parent/name).read_text())
            fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='download_with_system_trust')
            env={'os':types.SimpleNamespace(name='nt',environ={}), 'urllib':urllib,'Path':Path,'subprocess':subprocess}
            exec(compile(ast.Module(body=[fn],type_ignores=[]),name,'exec'),env)
            yield env['download_with_system_trust'],env
    def test_normal_download_no_fallback(self):
        for fn,env in self.functions():
            with patch('urllib.request.urlretrieve') as retrieve,patch('subprocess.run') as run:
                fn('https://example.invalid/file',Path('file'))
                retrieve.assert_called_once();run.assert_not_called()
    def test_certificate_error_retries_with_validation(self):
        for fn,env in self.functions():
            error=urllib.error.URLError(ssl.SSLCertVerificationError(1,'issuer unavailable'))
            with patch('urllib.request.urlretrieve',side_effect=error),patch('subprocess.run',return_value=types.SimpleNamespace(returncode=0)) as run:
                fn('https://example.invalid/file',Path("space's/file"))
                call=run.call_args;script=call.args[0][-1]
                self.assertNotIn('SkipCertificateCheck',script)
                self.assertNotIn('ServerCertificateValidationCallback',script)
                self.assertNotIn("space's",script)
                self.assertEqual(call.kwargs['env']['MEDIAUTO_DOWNLOAD_URL'],'https://example.invalid/file')
    def test_linux_or_non_certificate_error_does_not_fallback(self):
        for fn,env in self.functions():
            for windows,error in [(False,ssl.SSLCertVerificationError(1,'bad cert')),(True,OSError('offline'))]:
                env['os'].name='nt' if windows else 'posix'
                with patch('urllib.request.urlretrieve',side_effect=urllib.error.URLError(error)),patch('subprocess.run') as run:
                    with self.assertRaises(urllib.error.URLError):fn('https://example.invalid',Path('file'))
                    run.assert_not_called()
    def test_windows_failure_is_not_ignored(self):
        for fn,env in self.functions():
            with patch('urllib.request.urlretrieve',side_effect=ssl.SSLCertVerificationError(1,'bad cert')),patch('subprocess.run',return_value=types.SimpleNamespace(returncode=1)):
                with self.assertRaisesRegex(RuntimeError,'not disabled'):fn('https://example.invalid',Path('file'))
