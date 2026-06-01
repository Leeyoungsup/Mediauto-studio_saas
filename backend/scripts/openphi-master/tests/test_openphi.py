# !/usr/bin/env python3
# -*- coding: utf-8 -*-

"""

OpenPhi, an API to access Philips iSyntax images.

Note that the SDK (v2.0-L1) should be preliminarly installed:
https://www.openpathology.philips.com/.

This module roughly follows the OpenSlide Python API, see documentation at:
https://openslide.org/api/python/.

WARNING: The class is not thread-safe!

Kimmo Kartasalo, kimmo.kartasalo@gmail.com,
Nita Mulliqi, mulliqi.nita@gmail.com.

2024-02-02

"""

from openphi.openphi import OpenPhi
import unittest

# Test opening files.
class FileTests(unittest.TestCase):    
    def test_folder(self):
        self.assertRaises(AssertionError, lambda: OpenPhi("tests"))
    
    def test_nofile(self):
        self.assertRaises(AssertionError, lambda: OpenPhi("tests/missing.isyntax"))

    def test_noisyntax(self):
        self.assertRaises(AssertionError, lambda: OpenPhi("tests/testslide.tiff"))
        
    def test_invalidview(self):
        self.assertRaises(AssertionError, lambda: OpenPhi("tests/testslide.isyntax", view='fobar'))

# Open and close the OpenPhi object of the test image for every test case.
# SlideTests inherits these and applies them to each test case.
class _iSyntaxTest(object):
    def setUp(self):
        self.slide = OpenPhi(self.INPUTFILE)

    def tearDown(self):
        self.slide.close()
        
# Open and close the OpenPhi object of the test image for every test case.
# Use the display view of the WSI instead of the source view i.e. post-processed
# image data instead of raw image data.
# SlideTests inherits these and applies them to each test case.
class _iSyntaxTestDisplayView(object):
    def setUp(self):
        self.slide = OpenPhi(self.INPUTFILE, view='display')

    def tearDown(self):
        self.slide.close()

# Test methods on a real .isyntax file using the source view.
class SlideTests(_iSyntaxTest, unittest.TestCase):
    INPUTFILE = "tests/testslide.isyntax"
    
    # Test basic metadata populated when opening an image.
    def test_dimensions(self):
        self.assertEqual(self.slide.level_count, 8)
        self.assertEqual(self.slide.dimensions, (37382, 73222))
        self.assertEqual(self.slide.level_dimensions,
                        [(37382, 73222), (18689, 36609), (9342, 18302), 
                          (4669, 9149), (2333, 4573), (1165, 2285), 
                          (581, 1141), (289, 569)])
        self.assertEqual(self.slide.level_downsamples,
                          [1, 2, 4, 8, 16, 32, 64, 128])

    # Test extraction of full metadata.
    def test_properties(self):
        self.assertEqual(self.slide.properties['openslide.bounds-height'], '73222')
        self.assertEqual(self.slide.properties['openslide.bounds-width'], '37382')
        self.assertEqual(self.slide.properties['openslide.bounds-x'], '0')
        self.assertEqual(self.slide.properties['openslide.bounds-y'], '0')
        self.assertEqual(self.slide.properties['openslide.comment'], '             ')
        self.assertEqual(self.slide.properties['openslide.mpp-x'], '0.25')
        self.assertEqual(self.slide.properties['openslide.mpp-y'], '0.25')
        self.assertEqual(self.slide.properties['openslide.objective-power'], '40')
        self.assertEqual(self.slide.properties['openslide.quickhash-1'], '')
        self.assertEqual(self.slide.properties['openslide.vendor'], 'PHILIPS')
        self.assertEqual(self.slide.properties['DICOM_ACQUISITION_DATETIME'],'20210609111602.000000')
        self.assertEqual(self.slide.properties['DICOM_MANUFACTURERS_MODEL_NAME'], 'UFS Scanner')
        self.assertEqual(self.slide.properties['DICOM_DEVICE_SERIAL_NUMBER'], 'FMT0586')

    # Test label and macro images.
    def test_associated_images(self):
        self.assertEqual(self.slide.associated_images['label'].size, (783, 733))
        self.assertEqual(self.slide.associated_images['macro'].size, (1678, 799))
        
    # Test extraction of thumbnail.
    def test_thumbnail(self):
        self.assertEqual(self.slide.get_thumbnail((2000, 2000)).size, (581, 1141))
        self.assertEqual(self.slide.get_thumbnail((256, 256)).size, (256, 256))

    # Test extraction of thumbnail - bad parameters.
    def test_thumbnail_errors(self):
        # Width is negative.
        self.assertRaises(AssertionError,
                          lambda: self.slide.get_thumbnail((-1,2000)))
        # Height is negative.
        self.assertRaises(AssertionError,
                          lambda: self.slide.get_thumbnail((2000,-1)))
 
    # Test getting best downsampling factor.
    def test_get_best_level_for_downsample(self):
        self.assertEqual(self.slide.get_best_level_for_downsample(0.9), 0)
        self.assertEqual(self.slide.get_best_level_for_downsample(1), 0)
        self.assertEqual(self.slide.get_best_level_for_downsample(1.2), 0)
        self.assertEqual(self.slide.get_best_level_for_downsample(2), 1)
        self.assertEqual(self.slide.get_best_level_for_downsample(4.5), 2)
        self.assertEqual(self.slide.get_best_level_for_downsample(1000000), 7)

    # Test getting best downsampling factor. - bad parameters.
    def test_get_best_level_for_downsample_errors(self):
        # Downsampling factor is negative.
        self.assertRaises(AssertionError,
                          lambda: self.slide.get_best_level_for_downsample(-1))
        # Downsampling factor is zero.
        self.assertRaises(AssertionError,
                          lambda: self.slide.get_best_level_for_downsample(0))
        # Downsampling factor is not numerical.
        self.assertRaises(AssertionError,
                          lambda: self.slide.get_best_level_for_downsample('abc'))
        
    # Test reading entire WSI.
    def test_read_wsi(self):
        wsi = self.slide.read_wsi(level=4, bgvalue=255, channels="RGBA")
        self.assertEqual(wsi.size, (2333, 4573))
        self.assertEqual(wsi.mode, "RGBA")
        
        wsi = self.slide.read_wsi(level=4, bgvalue=255, channels="RGB")
        self.assertEqual(wsi.size, (2333, 4573))
        self.assertEqual(wsi.mode, "RGB")
    
    # Test reading entire WSI - bad parameters.
    def test_read_wsi_errors(self):
        # Level is not integer.
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_wsi(level=0.5, bgvalue=255, channels="RGB"))
        # Level is negative.
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_wsi(level=-1, bgvalue=255, channels="RGB"))
        # Channels is not RGB or RGBA.
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_wsi(level=4, bgvalue=255, channels="ABC"))
        # Bgvalue is negative.
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_wsi(level=4, bgvalue=-1, channels="RGB"))
        
    # Test reading a region.
    def test_read_region(self):
        tile = self.slide.read_region((64,64), 0, (100,100))
        self.assertEqual(tile.size, (100,100))
        self.assertEqual(tile.mode, "RGBA")
        
        tile = self.slide.read_region((64,64), 4, (100,100))
        self.assertEqual(tile.size, (100,100))
        self.assertEqual(tile.mode, "RGBA")
        
        tile = self.slide.read_region((63,63), 0, (100,100))
        self.assertEqual(tile.size, (100,100))
        self.assertEqual(tile.mode, "RGBA")
        
        tile = self.slide.read_region((63,63), 4, (100,100))
        self.assertEqual(tile.size, (100,100))
        self.assertEqual(tile.mode, "RGBA")
        
    # Test reading a region - bad parameters.
    def test_read_region_errors(self):
        # Level is not integer.
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_region((64,64), 0.5, (100,100)))
        # Level is negative.
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_region((64,64), -1, (100,100)))
        # Location is not integer.
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_region((64.5,64), 0, (100,100)))
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_region((64,64.5), 0, (100,100)))
        # Location is negative.
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_region((-1,64), 0, (100,100)))
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_region((64,-1), 0, (100,100)))
        # Size is not integer.
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_region((64,64), 0, (100.1,100)))
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_region((64,64), 0, (100,100.1)))
        # Size is negative.
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_region((64,64), 0, (-1,100)))
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_region((64,64), 0, (100,-1)))
        
# Test methods on a real .isyntax file using the display view.
class SlideTestsDisplayView(_iSyntaxTestDisplayView, unittest.TestCase):
    INPUTFILE = "tests/testslide.isyntax"
    
    # Test basic metadata populated when opening an image.
    def test_dimensions(self):
        self.assertEqual(self.slide.level_count, 8)
        self.assertEqual(self.slide.dimensions, (37378, 73218))
        self.assertEqual(self.slide.level_dimensions,
                        [(37378, 73218), (18685, 36605), (9338, 18298), 
                          (4665, 9145), (2329, 4569), (1161, 2281), 
                          (577, 1137), (285, 565)])
        self.assertEqual(self.slide.level_downsamples,
                          [1, 2, 4, 8, 16, 32, 64, 128])

    # Test extraction of full metadata.
    def test_properties(self):
        self.assertEqual(self.slide.properties['openslide.bounds-height'], '73220')
        self.assertEqual(self.slide.properties['openslide.bounds-width'], '37380')
        self.assertEqual(self.slide.properties['openslide.bounds-x'], '0')
        self.assertEqual(self.slide.properties['openslide.bounds-y'], '0')
        self.assertEqual(self.slide.properties['openslide.comment'], '             ')
        self.assertEqual(self.slide.properties['openslide.mpp-x'], '0.25')
        self.assertEqual(self.slide.properties['openslide.mpp-y'], '0.25')
        self.assertEqual(self.slide.properties['openslide.objective-power'], '40')
        self.assertEqual(self.slide.properties['openslide.quickhash-1'], '')
        self.assertEqual(self.slide.properties['openslide.vendor'], 'PHILIPS')
        self.assertEqual(self.slide.properties['DICOM_ACQUISITION_DATETIME'],'20210609111602.000000')
        self.assertEqual(self.slide.properties['DICOM_MANUFACTURERS_MODEL_NAME'], 'UFS Scanner')
        self.assertEqual(self.slide.properties['DICOM_DEVICE_SERIAL_NUMBER'], 'FMT0586')

    # Test label and macro images.
    def test_associated_images(self):
        self.assertEqual(self.slide.associated_images['label'].size, (783, 733))
        self.assertEqual(self.slide.associated_images['macro'].size, (1678, 799))
        
    # Test extraction of thumbnail.
    def test_thumbnail(self):
        self.assertEqual(self.slide.get_thumbnail((2000, 2000)).size, (577, 1137))
        self.assertEqual(self.slide.get_thumbnail((256, 256)).size, (256, 256))

    # Test extraction of thumbnail - bad parameters.
    def test_thumbnail_errors(self):
        # Width is negative.
        self.assertRaises(AssertionError,
                          lambda: self.slide.get_thumbnail((-1,2000)))
        # Height is negative.
        self.assertRaises(AssertionError,
                          lambda: self.slide.get_thumbnail((2000,-1)))
 
    # Test getting best downsampling factor.
    def test_get_best_level_for_downsample(self):
        self.assertEqual(self.slide.get_best_level_for_downsample(0.9), 0)
        self.assertEqual(self.slide.get_best_level_for_downsample(1), 0)
        self.assertEqual(self.slide.get_best_level_for_downsample(1.2), 0)
        self.assertEqual(self.slide.get_best_level_for_downsample(2), 1)
        self.assertEqual(self.slide.get_best_level_for_downsample(4.5), 2)
        self.assertEqual(self.slide.get_best_level_for_downsample(1000000), 7)

    # Test getting best downsampling factor. - bad parameters.
    def test_get_best_level_for_downsample_errors(self):
        # Downsampling factor is negative.
        self.assertRaises(AssertionError,
                          lambda: self.slide.get_best_level_for_downsample(-1))
        # Downsampling factor is zero.
        self.assertRaises(AssertionError,
                          lambda: self.slide.get_best_level_for_downsample(0))
        # Downsampling factor is not numerical.
        self.assertRaises(AssertionError,
                          lambda: self.slide.get_best_level_for_downsample('abc'))
        
    # Test reading entire WSI.
    def test_read_wsi(self):
        wsi = self.slide.read_wsi(level=4, bgvalue=255, channels="RGBA")
        self.assertEqual(wsi.size, (2329, 4569))
        self.assertEqual(wsi.mode, "RGBA")
        
        wsi = self.slide.read_wsi(level=4, bgvalue=255, channels="RGB")
        self.assertEqual(wsi.size, (2329, 4569))
        self.assertEqual(wsi.mode, "RGB")
    
    # Test reading entire WSI - bad parameters.
    def test_read_wsi_errors(self):
        # Level is not integer.
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_wsi(level=0.5, bgvalue=255, channels="RGB"))
        # Level is negative.
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_wsi(level=-1, bgvalue=255, channels="RGB"))
        # Channels is not RGB or RGBA.
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_wsi(level=4, bgvalue=255, channels="ABC"))
        # Bgvalue is negative.
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_wsi(level=4, bgvalue=-1, channels="RGB"))
        
    # Test reading a region.
    def test_read_region(self):
        tile = self.slide.read_region((64,64), 0, (100,100))
        self.assertEqual(tile.size, (100,100))
        self.assertEqual(tile.mode, "RGBA")
        
        tile = self.slide.read_region((64,64), 4, (100,100))
        self.assertEqual(tile.size, (100,100))
        self.assertEqual(tile.mode, "RGBA")
        
        tile = self.slide.read_region((63,63), 0, (100,100))
        self.assertEqual(tile.size, (100,100))
        self.assertEqual(tile.mode, "RGBA")
        
        tile = self.slide.read_region((63,63), 4, (100,100))
        self.assertEqual(tile.size, (100,100))
        self.assertEqual(tile.mode, "RGBA")
        
    # Test reading a region - bad parameters.
    def test_read_region_errors(self):
        # Level is not integer.
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_region((64,64), 0.5, (100,100)))
        # Level is negative.
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_region((64,64), -1, (100,100)))
        # Location is not integer.
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_region((64.5,64), 0, (100,100)))
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_region((64,64.5), 0, (100,100)))
        # Location is negative.
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_region((-1,64), 0, (100,100)))
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_region((64,-1), 0, (100,100)))
        # Size is not integer.
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_region((64,64), 0, (100.1,100)))
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_region((64,64), 0, (100,100.1)))
        # Size is negative.
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_region((64,64), 0, (-1,100)))
        self.assertRaises(AssertionError,
                          lambda: self.slide.read_region((64,64), 0, (100,-1)))
        
if __name__ == '__main__':
    unittest.main()
