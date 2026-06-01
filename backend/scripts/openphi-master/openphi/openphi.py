# !/usr/bin/env python3
# -*- coding: utf-8 -*-

"""

OpenPhi, an API to access Philips iSyntax images.

Note that the SDK (v2.0-L1) should be preliminarily installed:
https://www.openpathology.philips.com/.

This module roughly follows the OpenSlide Python API, see documentation at:
https://openslide.org/api/python/.

WARNING: The class is not thread-safe!

Kimmo Kartasalo, kimmo.kartasalo@gmail.com,
Nita Mulliqi, mulliqi.nita@gmail.com.

2024-02-02

"""

# Import Philips SDK modules.
import PIL.Image
import pixelengine
import softwarerenderbackend
import softwarerendercontext

# These modules are needed for GPU-accelerated rendering.
# import eglrendercontext
# import gles2renderbackend
# import gles3renderbackend

# Import other modules.
from io import BytesIO
import numpy as np
from os import path
from PIL import Image

class OpenPhi:

    def __init__(self, inputfilename, view='source'):
        try:
            assert (isinstance(view, (str)) and (view == 'source' or view == 'display')), "view must be 'source' or 'display'!"
            assert (path.isfile(inputfilename)), "Input " + inputfilename + " is not a file!"
            assert (path.splitext(inputfilename)[1] == ".isyntax"), "Input " + inputfilename + " is not an .isyntax file!"
                    
            render_context = softwarerendercontext.SoftwareRenderContext()
            render_backend = softwarerenderbackend.SoftwareRenderBackend()
            pixel_engine = pixelengine.PixelEngine(render_backend, render_context)

            self.pe = pixel_engine

            # Use ficom container to avoid needing write permissions for cache files.
            self.pe["in"].open(inputfilename, "ficom")
            
            if view == 'source':
                self.view_wsi = self.pe["in"]['WSI'].source_view
            elif view == 'display':
                self.view_wsi = self.pe["in"]['WSI'].display_view
                self.view_wsi.load_default_parameters()
            
            self.view_label = self.pe["in"]['LABELIMAGE'].source_view
            self.view_macro = self.pe["in"]['MACROIMAGE'].source_view

            # Find out what numerical indices correspond to.
            self.__init_indices()

            # Get spatial properties.
            self.__init_dimensions()

            # Get metadata properties.
            self.__init_properties()

            # Get macro and label images.
            self.__init_associated_images()

        except AssertionError as error:
            print("Check input file!")
            print(error)
            raise

    # Get indices of images and dimensions in iSyntax file.
    def __init_indices(self):
        # Figure out which index corresponds to which image.
        for i in range(self.pe["in"].num_images):
            if self.pe["in"][i].image_type == 'WSI':
                self.wsiind = i
            elif self.pe["in"][i].image_type == 'LABELIMAGE':
                self.labelind = i
            elif self.pe["in"][i].image_type == 'MACROIMAGE':
                self.macroind = i
            else:
                print("Unknown image type: " + self.pe["in"][i].image_type)

        # Figure out which index corresponds to which axis.
        self.xind = self.view_wsi.dimension_names.index('x')
        self.yind = self.view_wsi.dimension_names.index('y')

    # Get spatial properties of the image.
    def __init_dimensions(self):
        # Get number of resolution levels.
        self.level_count = self.view_wsi.num_derived_levels
        # Get pixel dimensions and downsampling factors of all levels.
        self.level_dimensions = []
        self.level_downsamples = []
        for lev in range(self.level_count):
            # Get step size between pixels for this level (in full-res pixels).
            step = self.view_wsi.dimension_ranges(lev)[self.xind][1]
            # Get start and end coordinates of this level (in full-res pixels).
            startx = self.view_wsi.dimension_ranges(lev)[self.xind][0]
            endx = self.view_wsi.dimension_ranges(lev)[self.xind][2]
            starty = self.view_wsi.dimension_ranges(lev)[self.yind][0]
            endy = self.view_wsi.dimension_ranges(lev)[self.yind][2]
            # Get the dimensions of this level (in full-res pixels), divide by
            # step size to get the actual pixel dimensions in level's pixels.
            dims = (int(1 + (endx - startx) / step),
                    int(1 + (endy - starty) / step))

            # Append the pixel dimensions of this level to the list.
            self.level_dimensions.append(dims)

            # Append the downsampling factor of this level to the list.
            self.level_downsamples.append(step)

            # Pixel dimensions of level 0 are also stored separately.
            if lev == 0:
                self.dimensions = dims

    # Get metadata properties of the image.
    def __init_properties(self):
        self.properties = dict()
        # The height of the rectangle bounding the non-empty region of the slide.
        self.properties['openslide.bounds-height'] = str(self.view_wsi.dimension_ranges(0)[self.yind][-1] + 1)
        # The width of the rectangle bounding the non-empty region of the slide.
        self.properties['openslide.bounds-width'] = str(self.view_wsi.dimension_ranges(0)[self.xind][-1] + 1)
        # The X coordinate of the rectangle bounding the non-empty region of the slide.
        # In iSyntax the coordinate system of the WSI always starts from (0,0).
        self.properties['openslide.bounds-x'] = str(0)
        # The Y coordinate of the rectangle bounding the non-empty region of the slide.
        # In iSyntax the coordinate system of the WSI always starts from (0,0).
        self.properties['openslide.bounds-y'] = str(0)
        # The number of microns per pixel in the X dimension of level 0.
        self.properties['openslide.mpp-x'] = str(self.view_wsi.scale[self.xind])
        # The number of microns per pixel in the Y dimension of level 0.
        self.properties['openslide.mpp-y'] = str(self.view_wsi.scale[self.yind])
        # A slide’s objective power. Should always be 40 for Philips?
        self.properties['openslide.objective-power'] = str(40)
        # The “quickhash-1” sum.
        self.properties['openslide.quickhash-1'] = str('')
        # An identification of the vendor.
        self.properties['openslide.vendor'] = str(self.pe["in"].manufacturer)
        # Use the comment field to store the barcode if it exists.
        try:
            self.properties['openslide.comment'] = str(self.pe["in"].barcode)
        except:
            self.properties['openslide.comment'] = str('')
        # DICOM acquisition time.
        try:
            self.properties['DICOM_ACQUISITION_DATETIME'] = str(self.pe["in"].acquisition_datetime)
        except:
            self.properties['DICOM_ACQUISITION_DATETIME'] = str('')
        # DICOM scanner model.
        try:
            self.properties['DICOM_MANUFACTURERS_MODEL_NAME'] = str(self.pe["in"].model_name)
        except:
            self.properties['DICOM_MANUFACTURERS_MODEL_NAME'] = str('')
        # DICOM scanner serial number.
        try:
            self.properties['DICOM_DEVICE_SERIAL_NUMBER'] = str(self.pe["in"].device_serial_number)
        except:
            self.properties['DICOM_DEVICE_SERIAL_NUMBER'] = str('')

    # Get macro and label images.
    def __init_associated_images(self):
        self.associated_images = dict()
        # Get the JPEG-compressed bytestream, then decompress as PIL.Image.
        self.associated_images['label'] = Image.open(BytesIO(self.pe["in"][self.labelind].image_data))
        self.associated_images['macro'] = Image.open(BytesIO(self.pe["in"][self.macroind].image_data))

    def get_best_level_for_downsample(self, downsample):
        """Method returns the index of best level to use for a given downsampling factor.

        @param: downsample required downsampling factor.

        """
        try:
            assert (isinstance(downsample, (int, np.integer, float)) and downsample > 0), "Downsample should be a positive number."
            
            # If upsampling is required, stick to the highest resolution level.
            if downsample <= 1.0:
                return 0
            
            # Return the level with downsampling factor equal to or less than
            # the required downsampling factor.
            for level, downsampling_level in enumerate(self.level_downsamples):
                if downsampling_level > downsample:
                    return level - 1
            
            # If no such level is found, return the index of the lowest resolution
            # level present.
            return self.level_count - 1
        
        except AssertionError as error:
            print("Incorrect input parameter!")
            print(error)
            raise

    def get_thumbnail(self, size=(4000, 4000)):
        """Method returns RGB thumbnail of the entire WSI as PIL image.

        @param: size maximum width and height of thumbnail WSI.

        """

        try:
            assert (isinstance(size[0], (int, np.integer)) and size[0] > 0), "Size should be a positive integer."
            assert (isinstance(size[1], (int, np.integer)) and size[1] > 0), "Size should be a positive integer."

            # Take the first index (highest res level) where both X and Y dimension
            # are smaller or equal to the specified maximum dimensions.
            # If there is no such level, take the lowest res level.
            level = len(self.level_dimensions) - 1
            for index, dim in enumerate(self.level_dimensions):
                if dim[0] <= size[0] and dim[1] <= size[1]:
                    level = index
                    break

            # Coordinates of the entire WSI view available for the desired level.
            # x-start, x-end, y-start, y-end, level
            roicoords = [[self.view_wsi.dimension_ranges(level)[self.xind][0],
                        self.view_wsi.dimension_ranges(level)[self.xind][2],
                        self.view_wsi.dimension_ranges(level)[self.yind][0],
                        self.view_wsi.dimension_ranges(level)[self.yind][2],
                        level]]

            image = self.__read_pixeldata(roicoords=roicoords,
                                        level=level,
                                        bgvalue=255,
                                        channels="RGB")

            if image.width > size[0] or image.height > size[1]:
                image = image.resize(size, PIL.Image.BILINEAR)

            return image

        except AssertionError as error:
            print("Incorrect input parameter!")
            print(error)
            raise

    def read_wsi(self, level=4, bgvalue=255, channels="RGBA"):
        """Method returns the entire WSI at desired resolution level as PIL image.

        @param: level the desired resolution level.
        @param: bgvalue background color used in the RGB channel format.
        @param: channels RBG or RGBA channel format.

        """

        try:
            assert (isinstance(level, (int, np.integer)) and level >= 0), "Level should be a non-negative integer."
            assert (isinstance(bgvalue, (int, np.integer)) and bgvalue > 0), "Bgvalue should be a positive integer."
            assert (channels == "RGBA" or channels == "RGB"), "Only RGB or RGBA channel formats are supported."

            # Coordinates of the entire WSI view available for the desired level.
            # x-start, x-end, y-start, y-end, level
            # List of lists, one list per ROI.
            roicoords = [[self.view_wsi.dimension_ranges(level)[self.xind][0],
                        self.view_wsi.dimension_ranges(level)[self.xind][2],
                        self.view_wsi.dimension_ranges(level)[self.yind][0],
                        self.view_wsi.dimension_ranges(level)[self.yind][2],
                        level]]

            image = self.__read_pixeldata(roicoords=roicoords,
                                        level=level,
                                        bgvalue=bgvalue,
                                        channels=channels)
            return image

        except AssertionError as error:
            print("Incorrect input parameter!")
            print(error)
            raise

    def read_region(self, location, level, size):
        """Method returns rectangular region of the WSI at a desired resolution level as PIL image.

        @param: location top-left pixel values with reference to level 0.
        @param: level the desired resolution level.
        @param: size width and height of the region of interest.

        """

        try:
            assert (isinstance(location[0], (int, np.integer)) and location[0] >= 0), "Location should be a non-negative integer."
            assert (isinstance(location[1], (int, np.integer)) and location[1] >= 0), "Location should be a non-negative integer."
            assert (isinstance(level, (int, np.integer)) and level >= 0), "Level should be a non-negative integer."
            assert (isinstance(size[0], (int, np.integer)) and size[0] > 0), "Size should be a positive integer."
            assert (isinstance(size[1], (int, np.integer)) and size[1] > 0), "Size should be a positive integer."

            # Pixel spacing for this level.
            step = self.level_downsamples[level]

            # Coordinates of the region in full-res system
            # x-start, x-end, y-start, y-end. Make sure the x and y coordinate
            # are valid on the resolution level i.e. divisible by the level's 
            # pixel spacing. Ensure this by removing the modulus.
            roicoords = [[location[0] - location[0] % step,
                        location[0] - location[0] % step + size[0] * step - 2 ** level,
                        location[1] - location[1] % step,
                        location[1] - location[1] % step + size[1] * step - 2 ** level,
                        level]]

            image = self.__read_pixeldata(roicoords, level)

            return image

        except AssertionError as error:
            print("Incorrect input parameter!")
            print(error)
            raise

    def __read_pixeldata(self, roicoords, level, bgvalue=255, channels="RGBA"):
        """Method returns the actual pixel data for a given region as PIL image.

        @param: roicoords coordinates of pixel data for a given region.
        @param: level resolution level.
        @param: bgvalue background color used in the RGB channel format.
        @param: channels RBG or RGBA channel format.

        """

        if not (channels == "RGB" or channels == "RGBA"):
            print("Warning: unknown channel format " + str(channels) + ", using RGBA!")
            channels = "RGBA"
        # RGBA includes alpha channel (scanned = 255, non-scanned = 0).
        if channels == "RGBA":
            buffer = pixelengine.PixelEngine.BufferType.RGBA
            bgcolor = [bgvalue, bgvalue, bgvalue, 0]
        # RGB lacks alpha channel (non-scanned replaced by bgcolor).
        elif channels == "RGB":
            buffer = pixelengine.PixelEngine.BufferType.RGB
            bgcolor = [bgvalue, bgvalue, bgvalue]

        regions = self.view_wsi.request_regions(region=roicoords,
                                                data_envelopes=self.view_wsi.data_envelopes(level),
                                                enable_async_rendering=False,
                                                background_color=bgcolor,
                                                buffer_type=buffer)
        # Pixel spacing for this level.
        step = self.level_downsamples[level]

        # Get the final dimensions of the image in pixels.
        x_start, x_end, y_start, y_end, level = regions[0].range
        patch_width = int(1 + (x_end - x_start) / step)
        patch_height = int(1 + (y_end - y_start) / step)

        # Create empty buffer of correct size.
        pixels = np.empty(int(patch_width * patch_height * len(channels)), dtype=np.uint8)

        # Read raw bytestream.
        regions[0].get(pixels)
        # Decompress bytestream into a PIL.Image.
        image = Image.frombuffer(channels, (int(patch_width), int(patch_height)), pixels, 'raw', channels, 0, 1)

        return image

    # Close an image.
    def close(self):

        self.pe["in"].close()
