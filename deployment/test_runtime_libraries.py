import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('runtime_libraries',Path(__file__).parent/'native/runtime_libraries.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class RuntimeLibrariesTests(unittest.TestCase):
    def test_only_selected_conda_cpp_library_is_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            library=Path(directory)/'lib/libstdc++.so.6'
            library.parent.mkdir();library.write_bytes(b'fixture CXXABI_1.3.15')
            with patch.object(r.sys,'platform','linux'),patch.object(r.sys,'prefix',directory),patch.object(r.ctypes,'CDLL') as load:
                r.load_conda_cpp_runtime()
                load.assert_called_once_with(str(library),mode=r.ctypes.RTLD_GLOBAL)

    def test_missing_or_old_cpp_runtime_stops_before_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(r.sys,'platform','linux'),patch.object(r.sys,'prefix',directory),patch.object(r.ctypes,'CDLL') as load:
                with self.assertRaisesRegex(RuntimeError,'Rerun'):r.load_conda_cpp_runtime()
                library=Path(directory)/'lib/libstdc++.so.6'
                library.parent.mkdir();library.write_bytes(b'old CXXABI_1.3.13')
                with self.assertRaisesRegex(RuntimeError,'Rerun'):r.load_conda_cpp_runtime()
                load.assert_not_called()

    def test_windows_keeps_its_dll_handling(self):
        with patch.object(r.sys,'platform','win32'),patch.object(r.ctypes,'CDLL') as load:
            r.load_conda_cpp_runtime();load.assert_not_called()

    def test_migration_child_preloads_before_module_with_arguments_preserved(self):
        import runpy
        order=[]
        with patch.object(r.sys,'argv',['runtime_libraries.py','--module','alembic','upgrade','head']),patch.object(r,'load_conda_cpp_runtime',side_effect=lambda:order.append('cpp')),patch.object(runpy,'run_module',side_effect=lambda *a,**k:order.append(('module',r.sys.argv[:]))):
            r.main()
        self.assertEqual(order,['cpp',('module',['alembic','upgrade','head'])])

    def test_bootstrap_child_preloads_before_script(self):
        import runpy
        order=[]
        with patch.object(r.sys,'argv',['runtime_libraries.py','--script','bootstrap_admin.py','--strict-db']),patch.object(r,'load_conda_cpp_runtime',side_effect=lambda:order.append('cpp')),patch.object(runpy,'run_path',side_effect=lambda *a,**k:order.append(('script',r.sys.argv[:]))):
            r.main()
        self.assertEqual(order,['cpp',('script',['bootstrap_admin.py','--strict-db'])])
