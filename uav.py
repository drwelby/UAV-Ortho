#!/usr/bin/env python

import sys
import os
from PIL import Image
from BeautifulSoup import BeautifulSoup
from osgeo import gdal
from osgeo.gdalconst import *

sys.path.append("/home/mpfister/siftDemoV4")

import sift

siftpath = "/home/mpfister/siftDemoV4/sift <"
surfpath = "/home/mpfister/SURF-V1.0.9/surf.ln"

class Point(object):
    def __init__(self,x,y):
        self.x = x
        self.y = y
        self.geox = None
        self.geoy = None

class GCP(object):
    
    def __init__(self, sx, sy, dx, dy):
        self.src = Point(sx, sy)
        self.dest = Point(dx, dy)

        
    def georef(self, destimage):
        self.dest.geox = self.dest.x / destimage.xpixels * destimage.bounds.dx
        self.dest.geoy = self.dest.y / destimage.ypixels * destimage.bounds.dy
        
class Bounds(object):
    
    def dx(self):
        return self.east - self.west
    
    def dy(self):
        return self.north - self.south
        
        

class BaseImage(object):
    
    def __init__(self,filename):
        self.locators = None
        self.descriptors = None
        self.image = Image.open(filename)
        self.xpixels, self.ypixels = self.image.size
       
        
    def runsift(self):
        #save a grayscale image
        imsize = self.image.size
        im = self.image.resize((imsize[0]/10, imsize[1]/10))
        im = im.convert("L")
        im.save(self.filename + "_gray.pgm", "PPM")
        siftexec = siftpath + self.filename + "_gray.pgm >" + self.filename + "_result.txt"
        print siftexec
        os.system(siftexec)
        self.locators, self.descriptors = sift.read_features_from_file(self.filename + "_result.txt")
        
        
    def runSurf(self):
        #save a grayscale image
        im = self.image.convert("L")
        im.save(self.filename + "_gray.pgm", "PPM")  
        surfexec = surfpath + " -i " +  self.filename + "_gray.pgm" + " -o " + self.filename + "_result.txt"
        print surfexec
        os.system(surfexec)
        self.locators, self.descriptors = sift.read_features_from_file(self.filename + "_result.txt")
  
  
class UAVImageGTiff(BaseImage):
    """ A class representing an aerial image that has already been roughly positioned
        using the flight data and JJ's parse.py / gdal script"""
       
    def __init__(self,filename):
        BaseImage.__init__(self, filename)
        self.filepath = filename
        self.filename, self.fileext = filename.split(".") # probably should fix this to use os functions
        self.getImageBounds()
        self.gcps = []        
        self.matchtable = None
        
    def getImageBounds(self):
        ds = gdal.Open(self.filepath, GA_ReadOnly )
        geotransform = ds.GetGeoTransform()
        # approximate - does not factor in rotation yet
        # however the parse.py files aren't rotated since they are already warped
        self.bounds = Bounds()
        self.bounds.north = geotransform[3]
        self.bounds.south = geotransform[3] - geotransform[1] * ds.RasterXSize
        self.bounds.east = geotransform[0] + geotransform[5] * ds.RasterYSize
        self.bounds.west = geotransform[0]
        
        
    
    def findGCPs(self, controlimage):
        self.matchtable = sift.match(self.descriptors, controlimage.descriptors)
        for i in range(len(self.matchtable)):
            if self.matchtable[i] > 0:
                g = GCP(self.locators[i,0], self.locators[i,1], controlimage.locators[matchtable(i),0] , controlimage.locators[matchtable(i),0])
                self.gcps.append(g)
        
    def transformTo(self, controlimage):
        self.runsift()
        controlimage.runsift()
        self.findGCPs(controlimage)
        gcpstring = ""
        for g in self.gcps:
            g.georef(controlimage)
            gcpstring += "-gcp s% s% s% s% " % (g.src.x, g.src.y, g.dest.geox, g.dest.geoy)
        os.system("gdal_transform -t_srs 'EPSG:4326' %s %s %s" % (gcpstring, self.filename + self.fileext, self.filename + "_gcp.tif"))
        os.system("gdal_warp %s %s" % (self.filename + "_gcp.tif", self.filename + "_geo.tif"))
            
        
            
    def normalizeTo(self, controlimage, scale):
        """ scales the target image in memory to match closer to the control image size.
            this keeps the number of SIFT points comparable, and should reduce errors
            due to large differences in scale"""
            
        self.image = self.image.resize(controlimage.image.size * scale)

        
    
    

class UAVImageKml(BaseImage):
    """ Parses out the kml and then tries to fix it.
        This skips the gdal georeferencing"""
       
    def __init__(self,kmlfilename):
        self.kmlfile = kmlfilename
        self.filename, self.fileext = self.getimagename()
        self.bounds = self.getimagebounds()
        self.gcps = []
        self.soup = BeautifulSoup(self.filename)
        self.image = Image(self.filename)
        
    def getimagename(self):
        fullname = self.soup.find("groundoverlay").find("icon").find("href")
        pieces = fullname.split(".")
        return pieces[:-1], pieces[-1]

    def getimagebounds(self):
        self.bounds.north = float(self.soup.find("north"))
        self.bounds.south = float(self.soup.find("south"))
        self.bounds.east = float(self.soup.find("east"))
        self.bounds.west = float(self.soup.find("west"))
        self.bounds.rotation = float(self.soup.find("rotation"))
        
       
    

class ControlImage(BaseImage):
    def __init__(uavimage):
        
        self.filename  =  uavimage.filename + "_control"
        self.fileext = "jpg"
        self.bounds = Bounds()
        self.bounds.north = uavimage.bounds.north * 2 - uavimage.bounds.south
        self.bounds.south = uavimage.bounds.south * 2 - uavimage.bounds.north
        self.bounds.east = uavimage.bounds.east * 2 - uavimage.bounds.west
        self.bounds.west = uavimage.bounds.west * 2 - uavimage.bounds.east


class GDALControlImage(ControlImage):
    
    def __init__(self, uavimage, basefilepath):
        ControlImage.__init__(uavimage)
        gdaltrans = "gdal_translate -projwin %s %s %s %s %s %.%s" % (self.bounds.west,
                                                                    self.bounds.north,
                                                                    self.bounds.east,
                                                                    self.bounds.south,
                                                                    basefilepath,
                                                                    self.filename,
                                                                    self.fileext)
        os.system(gdaltrans)
        BaseImage.__init__(self,(join(self.filename,self.fileext)))


class WMSControlImage(ControlImage):
    
    def __init__(self, uavimage, wmsuri):
        ControlImage.__init__(uavimage)
    
        # make the wms request and save it
        
        BaseImage.__init__(self,(join(self.filename,".",self.fileext)))

class NAIPControlImage(BaseImage):
    
    def __init__(self, uavimage):
        self.filename  =  uavimage.filename + "_control"
        self.fileext = ".jpg"
        self.bounds = Bounds()
        self.bounds.north = uavimage.bounds.north * 2 - uavimage.bounds.south
        self.bounds.south = uavimage.bounds.south * 2 - uavimage.bounds.north
        self.bounds.east = uavimage.bounds.east * 2 - uavimage.bounds.west
        self.bounds.west = uavimage.bounds.west * 2 - uavimage.bounds.east

        
       
        #get the control image from NAIP WMS server with pycurl
        #make sure to get it in WMS84
        
        BaseImage.__init__(self,(join(self.filename,".",self.fileext)))
        
        
        
    def getWorld(self):
        north = self.bounds.north
        west = self.bounds.west
        east = self.bounds.east
        dx = image.size()[0]
        res = (east-west)/dx
        world = str(dx) + "\n"
        world += "0" + "\n"
        world += "0" + "\n"
        world += "-" + str(dx) + "\n"
        world += str(west) + "\n"
        world += str(north)
        return world
        
        
        




def run(uavimagefile): 
    uavimage = UAVImageGTiff(uavimagefile)
    uavcontrol = NAIPControlImage(uavimage)
    #uavcontrol = GDALControlImage(uavimage, "theone.tif")
    uavimage.normalizeTo(uavcontrol,1.5)
    uavimage.transformTo(uavcontrol)






