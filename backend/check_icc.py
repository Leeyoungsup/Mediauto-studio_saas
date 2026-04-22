"""NDPI / WSI 슬라이드의 ICC 프로파일 + 주요 메타데이터 진단.

사용법:
    python check_icc.py <path_to_slide>

출력:
    - color_profile 존재 여부 (None 이면 OpenSlide 가 ICC 를 노출하지 않음)
    - 프로파일 설명 (있을 경우)
    - openslide.* 주요 properties 중 색/감마 관련 항목
"""

import os
import sys
from pathlib import Path

# ── OpenSlide DLL 경로 설정 (openslide import 전에 실행) ──
PROJECT_ROOT = Path(__file__).parent.parent.parent
_dll_paths = [
    PROJECT_ROOT / "libs" / "openslide_lib" / "bin",
    PROJECT_ROOT / "libs",
]
for _dp in _dll_paths:
    if _dp.exists():
        os.environ['OPENSLIDE_PATH'] = str(_dp)
        break
_path_additions = [
    str(p) for p in _dll_paths
    if p.exists() and str(p) not in os.environ.get('PATH', '')
]
if _path_additions:
    os.environ['PATH'] = os.pathsep.join(_path_additions) + os.pathsep + os.environ.get('PATH', '')
for _dp in _dll_paths:
    if _dp.exists():
        try:
            os.add_dll_directory(str(_dp))
        except (AttributeError, OSError):
            pass


def main():
    if len(sys.argv) < 2:
        print("Usage: python check_icc.py <slide_path>")
        sys.exit(1)

    path_slide = Path('backend/uploads/IHC(PD-L1)/CODIPAI-STBX-SS-04335-I-PD-22.ndpi')
    if not path_slide.exists():
        print(f"파일 없음: {path_slide}")
        sys.exit(1)

    import openslide

    print(f"openslide-python: {openslide.__library_version__ if hasattr(openslide, '__library_version__') else '?'}")
    try:
        import openslide as _os
        print(f"openslide-python version: {_os.__version__}")
    except Exception:
        pass

    slide = openslide.OpenSlide(str(path_slide))
    print(f"\nvendor: {slide.properties.get('openslide.vendor')}")
    print(f"dimensions: {slide.dimensions}")

    obj_profile = getattr(slide, "color_profile", None)
    print(f"\ncolor_profile 속성 존재: {obj_profile is not None}")

    if obj_profile is not None:
        try:
            from PIL import ImageCms
            str_desc = ImageCms.getProfileDescription(obj_profile)
            str_copy = ImageCms.getProfileCopyright(obj_profile)
            print(f"  description: {str_desc}")
            print(f"  copyright: {str_copy}")
        except Exception as e:
            print(f"  프로파일 읽기 실패: {e}")
    else:
        print("  → Hamamatsu 뷰어와 색이 다른 주원인 가능")

    print("\n=== 색/감마 관련 properties ===")
    for str_k, str_v in slide.properties.items():
        str_kl = str_k.lower()
        if any(s in str_kl for s in ("color", "gamma", "icc", "white", "balance", "brightness", "contrast", "ndp")):
            print(f"  {str_k} = {str_v}")

    slide.close()


if __name__ == "__main__":
    main()
