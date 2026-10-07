"""Select the app's C++ runtime before GPU/image libraries bind system libstdc++."""
import ctypes
from pathlib import Path
import sys

_HANDLES = []


def load_conda_cpp_runtime():
    if not sys.platform.startswith('linux'):
        return
    library = Path(sys.prefix) / 'lib/libstdc++.so.6'
    if not library.is_file() or b'CXXABI_1.3.15' not in library.read_bytes():
        raise RuntimeError('Conda C++ runtime is missing or too old. Rerun the updated installer to prepare libstdcxx-ng>=14 and libgcc-ng>=14.')
    # Keep the handle alive and load before torch/OpenSlide/libvips. Do not alter
    # system libraries or LD_LIBRARY_PATH for unrelated programs/Philips Python.
    _HANDLES.append(ctypes.CDLL(str(library), mode=ctypes.RTLD_GLOBAL))


def check_asyncio():
    import asyncio
    import greenlet
    from sqlalchemy.ext.asyncio import AsyncConnection
    from sqlalchemy.util.concurrency import greenlet_spawn
    if asyncio.run(greenlet_spawn(lambda: 42)) != 42:
        raise RuntimeError('SQLAlchemy asyncio runtime check failed.')


def main():
    """Give migration/bootstrap child interpreters the same runtime selection."""
    import runpy
    mode, target = sys.argv[1:3]
    sys.argv = [target] + sys.argv[3:]
    load_conda_cpp_runtime()
    if mode == '--module':
        runpy.run_module(target, run_name='__main__', alter_sys=True)
    elif mode == '--script':
        runpy.run_path(target, run_name='__main__')
    else:
        raise ValueError('Expected --module or --script')


if __name__ == '__main__':
    main()
