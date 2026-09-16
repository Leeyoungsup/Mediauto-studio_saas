#!/usr/bin/env python
"""Install and validate the proprietary Philips Pathology SDK bridge.

The main application uses Python 3.12/3.10+, while the supplied Philips SDK
binary modules are ABI-locked to Python 3.8 on Linux and Python 3.7 on Windows.
This script must therefore run inside the dedicated Philips Conda environment.
"""

from __future__ import annotations

import argparse
import os
import shutil
import site
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path


PATH_BACKEND = Path(__file__).resolve().parent.parent
PATH_BRIDGE_CLI = PATH_BACKEND / "philips_bridge" / "philips_cli.py"
PATH_OPENPHI = PATH_BACKEND / "scripts" / "openphi-master"
STR_LINUX_SDK_DIR = "philips-pathologysdk-2.0-L1-ubuntu20_04_py38_research"
STR_WINDOWS_SDK_DIR = "philips-pathologysdk-2.0-L1-windows10-py37-research"


def _log(str_level, str_message):
    print("[{}] {}".format(str_level, str_message), flush=True)


def _env_enabled(str_name):
    return os.environ.get(str_name, "").strip().lower() in ("1", "true", "yes", "y")


def _expected_python_minor():
    return 7 if os.name == "nt" else 8


def _check_python_abi():
    int_expected = _expected_python_minor()
    if sys.version_info[:2] != (3, int_expected):
        raise RuntimeError(
            "Philips SDK requires Python 3.{} on {}; current interpreter is {}.{}.".format(
                int_expected,
                "Windows" if os.name == "nt" else "Linux",
                sys.version_info.major,
                sys.version_info.minor,
            )
        )


def _safe_extract_archive(path_archive, path_destination):
    path_destination = path_destination.resolve()

    def _validate(str_member):
        path_target = (path_destination / str_member).resolve()
        if os.path.commonpath([str(path_destination), str(path_target)]) != str(path_destination):
            raise ValueError("Unsafe path in Philips SDK archive: {}".format(str_member))

    if zipfile.is_zipfile(str(path_archive)):
        with zipfile.ZipFile(str(path_archive)) as obj_archive:
            for obj_info in obj_archive.infolist():
                _validate(obj_info.filename)
            obj_archive.extractall(str(path_destination))
        return
    if tarfile.is_tarfile(str(path_archive)):
        with tarfile.open(str(path_archive), "r:*") as obj_archive:
            for obj_info in obj_archive.getmembers():
                _validate(obj_info.name)
            obj_archive.extractall(str(path_destination))
        return
    raise ValueError("Philips SDK source must be a directory, ZIP, TAR, or TAR.GZ archive.")


def _find_sdk_root(path_source):
    str_expected = STR_WINDOWS_SDK_DIR if os.name == "nt" else STR_LINUX_SDK_DIR
    if path_source.name == str_expected and path_source.is_dir():
        return path_source
    path_direct = path_source / str_expected
    if path_direct.is_dir():
        return path_direct
    for path_candidate in path_source.rglob(str_expected):
        if path_candidate.is_dir():
            return path_candidate
    raise FileNotFoundError("Expected Philips SDK directory was not found: {}".format(str_expected))


def _copy_tree_contents(path_source, path_destination):
    path_destination.mkdir(parents=True, exist_ok=True)
    for path_item in path_source.iterdir():
        path_target = path_destination / path_item.name
        if path_item.is_dir() and not path_item.is_symlink():
            shutil.copytree(str(path_item), str(path_target), symlinks=True, dirs_exist_ok=True)
        elif path_item.is_symlink():
            path_target.unlink(missing_ok=True)
            os.symlink(os.readlink(str(path_item)), str(path_target))
        else:
            shutil.copy2(str(path_item), str(path_target))


def _ensure_linux_soname_links(path_lib):
    for path_versioned in path_lib.glob("lib*.so.*.*"):
        str_name = path_versioned.name
        str_base, str_version = str_name.split(".so.", 1)
        str_major = str_version.split(".", 1)[0]
        for str_link in ("{}.so".format(str_base), "{}.so.{}".format(str_base, str_major)):
            path_link = path_lib / str_link
            if path_link.exists() or path_link.is_symlink():
                path_link.unlink()
            os.symlink(path_versioned.name, str(path_link))


def _install_linux_debs(path_sdk):
    if shutil.which("dpkg-deb") is None:
        raise RuntimeError("dpkg-deb is required to install the Linux Philips SDK bundle.")
    list_debs = sorted((path_sdk / "pathologysdk-modules").glob("*.deb"))
    list_debs += sorted((path_sdk / "pathologysdk-python38-modules").glob("*.deb"))
    if not list_debs:
        raise FileNotFoundError("No Philips SDK .deb modules were found in {}".format(path_sdk))

    list_site_paths = site.getsitepackages()
    if not list_site_paths:
        raise RuntimeError("Could not resolve the Philips environment site-packages directory.")
    path_site_packages = Path(list_site_paths[0])
    path_env_lib = Path(sys.prefix) / "lib"
    with tempfile.TemporaryDirectory(prefix="mediauto-philips-") as str_temp:
        path_extract = Path(str_temp) / "extract"
        for path_deb in list_debs:
            if path_extract.exists():
                shutil.rmtree(str(path_extract))
            path_extract.mkdir(parents=True)
            subprocess.check_call(["dpkg-deb", "-x", str(path_deb), str(path_extract)])
            path_native = path_extract / "usr" / "local" / "lib"
            path_python = path_extract / "usr" / "lib" / "python3" / "dist-packages"
            if path_native.is_dir():
                _copy_tree_contents(path_native, path_env_lib)
            if path_python.is_dir():
                _copy_tree_contents(path_python, path_site_packages)
    _ensure_linux_soname_links(path_env_lib)


def _pip_install(list_arguments):
    subprocess.check_call([sys.executable, "-m", "pip", "install"] + list_arguments)


def _install_windows_modules(path_sdk):
    # The SDK's 64-bit native modules require the supplied Microsoft runtimes.
    for relative in ("VC2013Redistributable/vcredist_x64.exe", "VC2017Redistributable/vc_redist.x64.exe"):
        runtime = path_sdk / "Redistributables" / relative
        if not runtime.is_file():
            raise FileNotFoundError("Missing Philips runtime: {}".format(runtime))
        result = subprocess.run([str(runtime), "/install", "/quiet", "/norestart"])
        if result.returncode not in (0, 1638, 3010):
            raise RuntimeError("Philips VC runtime installation failed: {} (exit {})".format(relative, result.returncode))
        if result.returncode == 3010:
            raise RuntimeError("Philips VC runtime requires a Windows restart; reboot and run install.bat again.")
    path_modules = path_sdk / "Modules"
    list_modules = sorted(path.parent for path in path_modules.glob("*/setup.py"))
    if not list_modules:
        raise FileNotFoundError("No Philips Windows Python modules were found in {}".format(path_modules))
    for path_module in list_modules:
        _pip_install(["--no-deps", "--force-reinstall", str(path_module)])


def _install_sdk(path_sdk):
    _pip_install(["numpy<2", "Pillow>=8,<11", "setuptools<68", "wheel<0.42"])
    if os.name == "nt":
        _install_windows_modules(path_sdk)
    else:
        _install_linux_debs(path_sdk)
    _pip_install(["--no-deps", "--force-reinstall", str(PATH_OPENPHI)])


def _smoke_test():
    dict_env = os.environ.copy()
    if os.name == "nt":
        list_paths = [
            str(Path(sys.prefix)),
            str(Path(sys.prefix) / "Library" / "bin"),
            str(Path(sys.prefix) / "DLLs"),
        ]
        dict_env["PATH"] = os.pathsep.join(list_paths + [dict_env.get("PATH", "")])
    else:
        dict_env["LD_LIBRARY_PATH"] = os.pathsep.join([
            str(Path(sys.prefix) / "lib"),
            dict_env.get("LD_LIBRARY_PATH", ""),
        ])
    obj_result = subprocess.run(
        [sys.executable, str(PATH_BRIDGE_CLI), "smoke"],
        env=dict_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        timeout=60,
    )
    if obj_result.returncode != 0:
        raise RuntimeError(
            "Philips bridge smoke test failed:\n{}".format(
                (obj_result.stderr or obj_result.stdout).strip()
            )
        )
    str_output = (obj_result.stdout or "").strip()
    _log("OK", "Philips bridge smoke test passed: {}".format(str_output))


def main():
    obj_parser = argparse.ArgumentParser(description="Install/validate the Philips SDK bridge environment.")
    obj_parser.add_argument(
        "--sdk-source",
        default=os.environ.get("MEDIAUTO_PHILIPS_SDK_SOURCE", ""),
        help="Philips SDK directory or ZIP/TAR archive.",
    )
    obj_parser.add_argument("--check-only", action="store_true")
    obj_args = obj_parser.parse_args()

    try:
        _check_python_abi()
        if not obj_args.check_only:
            if not _env_enabled("MEDIAUTO_ACCEPT_PHILIPS_EULA"):
                raise RuntimeError(
                    "Set MEDIAUTO_ACCEPT_PHILIPS_EULA=1 only after reviewing and accepting the SDK EULA."
                )
            str_source = obj_args.sdk_source.strip()
            path_source = Path(str_source).expanduser().resolve() if str_source else PATH_BACKEND / "Philips_SDK"
            if not path_source.exists():
                raise FileNotFoundError(
                    "Philips SDK is not in Git. Set MEDIAUTO_PHILIPS_SDK_SOURCE to the licensed SDK bundle."
                )
            if path_source.is_dir():
                path_sdk = _find_sdk_root(path_source)
                _install_sdk(path_sdk)
            else:
                with tempfile.TemporaryDirectory(prefix="mediauto-philips-sdk-") as str_temp:
                    path_extract = Path(str_temp)
                    _safe_extract_archive(path_source, path_extract)
                    _install_sdk(_find_sdk_root(path_extract))
            _log("OK", "Philips SDK installed into {}.".format(sys.prefix))
        _smoke_test()
        return 0
    except Exception as obj_error:
        _log("ERROR", str(obj_error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
