from app.slide_manager import resolve_slide_vendor


def test_anonymized_source_vendor_precedes_openslide_vendor():
    assert resolve_slide_vendor({
        "aperio.WSI_Technical": '{"source_vendor":"hamamatsu"}',
        "openslide.vendor": "aperio",
    }) == "hamamatsu"


def test_image_description_wsi_technical_is_supported():
    assert resolve_slide_vendor({
        "tiff.ImageDescription": (
            "Aperio compatible WSI Anonymization|AppMag=40|"
            'WSI_Technical={"source_vendor":"leica","objective_power":40.0}'
        ),
        "openslide.vendor": "aperio",
    }) == "leica"


def test_openslide_vendor_is_used_without_source_vendor():
    assert resolve_slide_vendor({
        "aperio.WSI_Technical": '{"objective_power":40.0}',
        "openslide.vendor": "aperio",
    }) == "aperio"


def test_missing_or_placeholder_vendor_returns_unknown():
    assert resolve_slide_vendor({}) == "Unknown"
    assert resolve_slide_vendor({
        "aperio.WSI_Technical": '{"source_vendor":"Unknown"}',
        "openslide.vendor": "",
    }) == "Unknown"


def test_invalid_wsi_technical_falls_back_to_openslide_vendor():
    assert resolve_slide_vendor({
        "aperio.WSI_Technical": "not-json",
        "openslide.vendor": "generic-tiff",
    }) == "generic-tiff"
