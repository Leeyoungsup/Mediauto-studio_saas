"""Exercise runner output and failures in a separate interpreter."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HARNESS = '''import sys,types,runpy,socket,subprocess
sys.argv.pop(0)
sys.modules['runtime_libraries']=types.SimpleNamespace(load_conda_cpp_runtime=lambda: print('CPP LOAD'),check_asyncio=lambda: print('ASYNC CHECK'))
sys.modules['gpu_check']=types.SimpleNamespace(check_gpu=lambda: print('GPU CHECK'))
class Connection:
 def __enter__(self): return self
 def __exit__(self,*args): pass
socket.create_connection=lambda *a,**k:Connection()
def child(*a,**k):
 print('CHILD OUTPUT',file=k.get('stdout',sys.stdout))
subprocess.run=child
def serve(*a,**k):
 print('SERVER OUTPUT')
 raise RuntimeError('TEST APP FAILURE')
sys.modules['uvicorn']=types.SimpleNamespace(run=serve)
runpy.run_path(sys.argv[0],run_name='__main__')
'''

class RunnerTests(unittest.TestCase):
 def test_logging_console_and_preflight(self):
  runner=Path(__file__).parent/'native/runner.py'
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);settings=root/'app.json';log=root/'app.log'
   settings.write_text(json.dumps({'env':{},'backend':d,'log':str(log),'db_port':55432,'bind':'127.0.0.1','port':18093}))
   for mode in ('','--console','--check'):
    with self.subTest(mode=mode):
     args=[sys.executable,'-c',HARNESS,str(runner.resolve()),str(settings)]+([mode] if mode else [])
     result=subprocess.run(args,capture_output=True,text=True)
     output=log.read_text() if not mode and log.exists() else result.stdout+result.stderr
     self.assertLess(output.index('CPP LOAD') if 'CPP LOAD' in output else 0, output.index('ASYNC CHECK'))
     self.assertLess(output.index('GPU CHECK'), output.index('ASYNC CHECK'))
     if mode=='--check':
      self.assertEqual(result.returncode,0,output)
      self.assertNotIn('SERVER OUTPUT',output)
     else:
      self.assertEqual(result.returncode,1,output)
      for text in ('TEST APP FAILURE','SERVER OUTPUT'):self.assertIn(text,output)
      self.assertIn('CHILD OUTPUT',log.read_text())

if __name__=='__main__':unittest.main()
