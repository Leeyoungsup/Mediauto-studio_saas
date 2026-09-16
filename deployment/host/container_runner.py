"""Keep all app process output in rotating files in the host-mounted log directory."""
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import subprocess
import sys


def check_gpu():
    import torch
    import torchvision
    if not torch.cuda.is_available(): raise RuntimeError('CUDA GPU is unavailable; CPU fallback is disabled.')
    for i in range(torch.cuda.device_count()):
        device=f'cuda:{i}'
        x=torch.ones((8,8),device=device)
        if (x@x).sum().item()!=512: raise RuntimeError('CUDA matrix test failed.')
        boxes=torch.tensor([[0.,0.,2.,2.],[0.,0.,2.,2.]],device=device)
        scores=torch.tensor([0.9,0.8],device=device)
        if torchvision.ops.nms(boxes,scores,0.5).numel()!=1: raise RuntimeError('CUDA torchvision test failed.')
        torch.cuda.synchronize(i)
        logging.info('GPU %d ready: %s (CUDA %s)',i,torch.cuda.get_device_name(i),torch.version.cuda)


def main():
    Path('/logs').mkdir(parents=True,exist_ok=True)
    handler=RotatingFileHandler('/logs/app.log',maxBytes=20*1024*1024,backupCount=10,encoding='utf-8')
    logging.basicConfig(level=logging.INFO,handlers=[handler],format='%(asctime)s %(levelname)s %(message)s')
    child=None
    stopping=False
    def stop(signum,frame):
        nonlocal stopping
        stopping=True
        if child is not None and child.poll() is None:child.send_signal(signum)
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:
        check_gpu()
        commands=[[sys.executable,'-m','alembic','upgrade','head'],
                  [sys.executable,'/installer/bootstrap_admin.py','--strict-models','--strict-db'],
                  [sys.executable,'-m','uvicorn','main:app','--host','0.0.0.0','--port','8092']]
        for cmd in commands:
            if stopping:return
            child=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
            for line in child.stdout:logging.info('%s',line.rstrip())
            code=child.wait()
            if stopping:return
            if code:raise RuntimeError(f'Application process exited with code {code}')
    except Exception:
        logging.exception('GPU application startup failed')
        sys.exit(1)


if __name__=='__main__':main()
