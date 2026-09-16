import logging

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

