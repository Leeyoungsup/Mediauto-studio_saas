import importlib.util
import io
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).parent/'installer'
spec=importlib.util.spec_from_file_location('gui_contract',ROOT/'gui_contract.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)

class GuiTests(unittest.TestCase):
    def test_mixed_windows_log_encodings(self):
        message = '처리된 파일: C:\\MeDIAutoAI\\native\\.runtime\n'
        self.assertEqual(c.decode_log_line(message.encode('cp949'), ['cp949']), message)
        self.assertEqual(c.decode_log_line(message.encode('utf-8'), ['cp949']), message)
        event = c.PREFIX + json.dumps({'kind':'phase','text':'설치 준비'}, ensure_ascii=False) + '\n'
        self.assertEqual(c.decode_log_line(event.encode('utf-8'), ['cp949']), event)
        self.assertEqual(c.decode_log_line(b'Python OK\n', ['cp949']), 'Python OK\n')
        self.assertIn('\ufffd', c.decode_log_line(b'\xff', []))

    def test_native_and_python_output_share_pipe(self):
        native = '처리된 파일: C:\\설치\n'
        event = c.PREFIX + json.dumps({'kind':'phase','text':'설치 준비'}, ensure_ascii=False) + '\n'
        payload = native.encode('cp949') + event.encode('utf-8')
        process = subprocess.Popen([sys.executable, '-c', 'import sys; sys.stdout.buffer.write(' + repr(payload) + ')'],
                                   stdout=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
        with process.stdout:
            lines = [c.decode_log_line(raw, ['cp949']) for raw in iter(process.stdout.buffer.readline, b'')]
        self.assertEqual(process.wait(), 0)
        self.assertEqual(lines, [native, event])
        self.assertEqual(json.loads(lines[1][len(c.PREFIX):])['text'], '설치 준비')

    def values(self):
        return dict(mode='native',data_root='/data',model_path='/weights',slide_path='',app_port='18093',db_port='55432',bind='0.0.0.0',repository='owner/repo',ref='main',username='owner',token='private-PAT')
    def test_invalid_ports_and_missing_credentials(self):
        for changes in [dict(app_port='x'),dict(db_port='18093'),dict(app_port='65536'),dict(token=''),dict(repository='bad'),dict(ref='-bad')]:
            with self.assertRaises(ValueError):c.validate(dict(self.values(),**changes))
    def test_defaults_and_prompt_routing(self):
        values=self.values();c.validate(values)
        self.assertEqual(c.supplied_answer('Slide folder (Enter = /data/slides): ',values),'')
        self.assertEqual(c.supplied_answer('GitHub personal access token (PAT): ',values),'private-PAT')
        self.assertIsNone(c.supplied_answer('New PostgreSQL port [55433]: ',values))
        self.assertIsNone(c.supplied_answer('Have you reviewed and accepted this SDK license? [y/N]: ',values))
    def test_logs_redact_pat(self):
        self.assertEqual(c.redact('bad private-PAT token',self.values()),'bad [REDACTED] token')
    def test_worker_reuses_installer_prompts_and_no_secret_commandline(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(sys.modules,{'gui_contract':c}):
            root=Path(d);(root/'native').mkdir();(root/'native/install.py').write_text('''import getpass
assert input('External data root [/default]: ') == '/data'
assert getpass.getpass('GitHub personal access token (PAT): ') == 'private-PAT'
assert input('New PostgreSQL port [55433]: ') == '55443'
print('SIMULATED INSTALL COMPLETE')
''')
            spec=importlib.util.spec_from_file_location('gui_worker',ROOT/'gui_worker.py')
            w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w);w.__file__=str(root/'gui_worker.py')
            stdin=io.StringIO(json.dumps(self.values())+'\n'+json.dumps({'answer':'55443'})+'\n');stdout=io.StringIO()
            with patch('sys.stdin',stdin),patch('sys.stdout',stdout),patch.object(w.subprocess,'run') as run,patch.object(w.os,'geteuid',return_value=0),patch('builtins.input'),patch('getpass.getpass'),patch.object(sys,'argv',[]),patch.object(sys,'path',list(sys.path)):
                w.main()
            self.assertNotIn('private-PAT',stdout.getvalue())
            self.assertIn('"kind": "done"',stdout.getvalue())
            self.assertIn('New PostgreSQL port',stdout.getvalue())
            self.assertNotIn('private-PAT',str(run.call_args))
