#! /usr/bin/python

# ROS imports
import roslib
roslib.load_manifest( 'object_detector' )
import rospy

import sys
import math
import os.path
import time

import numpy as np
import cv

import yaml
import pygtk
pygtk.require('2.0')
import gtk
import gobject
from ResidualSaliencyFilter import ResidualSaliencyFilter
from abroun_gtk_gui.Display import Display
import PyBlobLib

#-------------------------------------------------------------------------------
class MainWindow:
    
    FOREGROUND_BRUSH_COLOUR = np.array( [ 255, 255, 0 ], dtype=np.uint8 )
    PROBABLY_FOREGROUND_BRUSH_COLOUR = np.array( [ 0, 255, 0 ], dtype=np.uint8 )
    BACKGROUND_BRUSH_COLOUR = np.array( [ 0, 0, 255 ], dtype=np.uint8 )
    
    # Classes of pixel in GrabCut algorithm
    GC_BGD = 0      # background
    GC_FGD = 1      # foreground
    GC_PR_BGD = 2   # most probably background
    GC_PR_FGD = 3   # most probably foreground 

    # GrabCut algorithm flags
    GC_INIT_WITH_RECT = 0
    GC_INIT_WITH_MASK = 1
    GC_EVAL = 2
 
    #---------------------------------------------------------------------------
    def __init__( self ):
    
        self.scriptPath = os.path.dirname( __file__ )
        self.image = None
        self.maskArray = None
        self.filename = None
        self.residualSaliencyFilter = ResidualSaliencyFilter()
            
        # Setup the GUI        
        builder = gtk.Builder()
        builder.add_from_file( self.scriptPath + "/GUI/SegmentationExplorer.glade" )
        
        self.window = builder.get_object( "winMain" )   
        dwgImage = builder.get_object( "dwgImage" )
        dwgSegmentation = builder.get_object( "dwgSegmentation" )
        dwgSaliency = builder.get_object( "dwgSaliency" )
        self.adjBrushSize = builder.get_object( "adjBrushSize" )
        self.comboBrushType = builder.get_object( "comboBrushType" )
        self.comboPixelClass = builder.get_object( "comboPixelClass" )
        
        self.dwgImageDisplay = Display( dwgImage )
        self.dwgSegmentationDisplay = Display( dwgSegmentation )
        self.dwgSaliencyDisplay = Display( dwgSaliency )
        
        # Set default values
        self.adjBrushSize.set_value( 1 )
        self.makeBrush()
        
        builder.connect_signals( self )
               
        updateLoop = self.update()
        gobject.idle_add( updateLoop.next )
        
        self.window.show()
        
    #---------------------------------------------------------------------------
    def onWinMainDestroy( self, widget, data = None ):  
        gtk.main_quit()
        
    #---------------------------------------------------------------------------   
    def main( self ):
        # All PyGTK applications must have a gtk.main(). Control ends here
        # and waits for an event to occur (like a key press or mouse event).
        gtk.main()
        
    #---------------------------------------------------------------------------
    def makeBrush( self ):
        
        brushSize = self.adjBrushSize.get_value()
        brushShape = ( brushSize, brushSize )
        self.brush = np.zeros( brushSize, dtype=np.uint8 )
        self.brush.fill( self.GC_FGD )
        
        brushRadius = int( brushSize / 2 )
        self.brushIndices = np.indices( brushShape ) - brushRadius
        brushType = self.comboBrushType.get_active_text()
        if brushType == "Circle":
            i = self.brushIndices
            circleIndices = np.where( i[0]*i[0] + i[1]*i[1] <= brushRadius*brushRadius )
            self.brushIndices = self.brushIndices[ :, circleIndices[ 0 ], circleIndices[ 1 ] ]
            
    #---------------------------------------------------------------------------
    def alterMask( self, x, y, pixelClass ):
        
        if self.maskArray != None:
            
            indices = np.copy( self.brushIndices )
            indices[ 0 ] += y
            indices[ 1 ] += x
            
            validIndices = indices[ :, 
                np.where( (indices[ 0 ]>=0) & (indices[ 1 ]>=0) \
                    & (indices[ 0 ] < self.maskArray.shape[ 0 ]) \
                    & (indices[ 1 ] < self.maskArray.shape[ 1 ]) ) ]
            self.maskArray[ validIndices[ 0 ], validIndices[ 1 ] ] = pixelClass
            
            self.redrawImageWithMask()
             
    #---------------------------------------------------------------------------
    def redrawImageWithMask( self ):
            self.composedImage = np.copy( self.image )
            self.composedImage[ self.maskArray == self.GC_FGD ] = self.FOREGROUND_BRUSH_COLOUR
            self.composedImage[ self.maskArray == self.GC_PR_FGD ] = self.PROBABLY_FOREGROUND_BRUSH_COLOUR
            self.composedImage[ self.maskArray == self.GC_BGD ] = self.BACKGROUND_BRUSH_COLOUR
            
            self.dwgImageDisplay.setImageFromNumpyArray( self.composedImage )
            
    #---------------------------------------------------------------------------
    def getCurPixelClass( self ):
        
        pixelClassText = self.comboPixelClass.get_active_text()
        if pixelClassText == "Background":
            return self.GC_BGD
        elif pixelClassText == "Probably Foreground":
            return self.GC_PR_FGD
        else:
            return self.GC_FGD
        
    #---------------------------------------------------------------------------
    def chooseImageFile( self ):
        
        result = None
        
        dialog = gtk.FileChooserDialog(
            title="Choose Image File",
            action=gtk.FILE_CHOOSER_ACTION_SAVE,
            buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT,
                      gtk.STOCK_OK, gtk.RESPONSE_ACCEPT) )

        dialog.set_current_folder( self.scriptPath + "/../../test_data/saliency" )
            
        filter = gtk.FileFilter()
        filter.add_pattern( "*.png" )
        filter.add_pattern( "*.bmp" )
        filter.add_pattern( "*.jpg" )
        filter.set_name( "Image Files" )
        dialog.add_filter( filter )
        dialog.set_filter( filter )
            
        result = dialog.run()

        if result == gtk.RESPONSE_ACCEPT:
            result = dialog.get_filename()

        dialog.destroy()
        
        return result
    
    #---------------------------------------------------------------------------
    def onMenuItemOpenImageActivate( self, widget ):
                
        filename = self.chooseImageFile()
        
        if filename != None:
            self.image = cv.LoadImageM( filename )
            cv.CvtColor( self.image, self.image, cv.CV_BGR2RGB )
            
            # Create a mask and blank segmentation that matches the size of the image
            self.maskArray = np.ones( ( self.image.height, self.image.width ), np.uint8 )*self.GC_PR_BGD
            self.segmentation = np.zeros( ( self.image.height, self.image.width, 3 ), np.uint8 )
            
            self.dwgImageDisplay.setImageFromOpenCVMatrix( self.image )
            self.dwgSegmentationDisplay.setImageFromNumpyArray( self.segmentation )            
    
    #---------------------------------------------------------------------------
    def onMenuItemOpenMaskActivate( self, widget ):
        
        # Map for translating mask values
        PIXEL_MAP = { 
            0 : self.GC_BGD,
            64 : self.GC_PR_BGD,
            128 : self.GC_PR_FGD,
            255 : self.GC_FGD }
           
        if self.image == None:
            return  # No image to apply mask to yet
            
        filename = self.chooseImageFile()
        
        if filename != None:
            maskImage = cv.LoadImageM( filename )
            if maskImage.width != self.image.width \
                or maskImage.height != self.image.height:
                    
                print "Error: Mask doesn't match the size of the current image"
                return
            
            #maskImageGray = cv.CreateMat( self.image.height, self.image.width, cv.CV_8UC1 )
            self.maskArray = np.ndarray( ( self.image.height, self.image.width ), np.uint8 )
            cv.CvtColor( maskImage, self.maskArray, cv.CV_BGR2GRAY )
            
            # Convert the pixel values over to the correct values for the pixel type
            translationArray = \
                [ ( self.maskArray == sourcePixelValue, PIXEL_MAP[ sourcePixelValue ] ) \
                    for sourcePixelValue in PIXEL_MAP ]
            for translation in translationArray:
                self.maskArray[ translation[ 0 ] ] = translation[ 1 ]
                
            # Redraw the main image to show the mask
            self.redrawImageWithMask()
    
    #---------------------------------------------------------------------------
    def onMenuItemQuitActivate( self, widget ):
        self.onWinMainDestroy( widget )
       
    #---------------------------------------------------------------------------
    def onBtnClearMaskClicked( self, widget ):
        if self.image != None:
            self.maskArray = np.ones( ( self.image.height, self.image.width ), np.uint8 )*self.GC_PR_BGD
            self.dwgImageDisplay.setImageFromOpenCVMatrix( self.image )
    
    #---------------------------------------------------------------------------
    def onBtnSegmentClicked( self, widget ):
        
        if self.maskArray != None:
            workingMask = np.copy( self.maskArray )
            
            fgModel = cv.CreateMat( 1, 5*13, cv.CV_64FC1 )
            cv.Set( fgModel, 0 )
            bgModel = cv.CreateMat( 1, 5*13, cv.CV_64FC1 )
            cv.Set( bgModel, 0 )
            
            workingImage = np.copy( self.image )
            cv.GrabCut( workingImage, workingMask, 
                (0,0,0,0), fgModel, bgModel, 12, self.GC_INIT_WITH_MASK )
            
            self.segmentation = np.copy( self.image )
            self.segmentation[ (workingMask != self.GC_PR_FGD) & (workingMask != self.GC_FGD) ] = 0
            self.dwgSegmentationDisplay.setImageFromNumpyArray( self.segmentation )
    
    #---------------------------------------------------------------------------
    def onBtnCreateSaliencyMaskClicked( self, widget ):
        
        ROI_X = 0
        ROI_Y = 76
        ROI_WIDTH = 230
        ROI_HEIGHT = 100
        
        #ROI_WIDTH = 10
        
        if self.image != None:
            
            # Create a saliency map from the current image
            grayImage = np.ndarray( ( self.image.height, self.image.width ), dtype=np.uint8 )
            cv.CvtColor( self.image, grayImage, cv.CV_RGB2GRAY )
            
            saliencyMap, largeSaliencyMap = self.residualSaliencyFilter.calcSaliencyMap( grayImage )
            self.dwgSaliencyDisplay.setImageFromNumpyArray( largeSaliencyMap )
        
            # Threshold to get blobs
            blobPixels = largeSaliencyMap >= 160
            largeSaliencyMap[ blobPixels ] = 255
            largeSaliencyMap[ blobPixels == False ] = 0
            
            # Label blobs
            largeSaliencyMap, numBlobs = PyBlobLib.labelBlobs( largeSaliencyMap )
            
            # Find blobs in the region of interest
            testMap = np.copy( largeSaliencyMap )
            testMap[ :ROI_Y, : ] = 0       # Mask out area above the ROI
            testMap[ :, :ROI_X ] = 0       # Mask out area to the left of the ROI
            testMap[ ROI_Y+ROI_HEIGHT: ] = 0   # Mask out area below the ROI
            testMap[ :, ROI_X+ROI_WIDTH: ] = 0   # Mask out area to the right of the ROI
        
            biggestBlobIdx = None
            biggestBlobSize = 0
        
            for blobIdx in range( 1, numBlobs + 1 ):
                if testMap[ testMap == blobIdx ].size > 0:
                    blobSize = largeSaliencyMap[ largeSaliencyMap == blobIdx ].size
                    if blobSize > biggestBlobSize:
                        biggestBlobSize = blobSize
                        biggestBlobIdx = blobIdx
        
            # Isolate the largest blob
            if biggestBlobIdx != None:
                biggestBlobPixels = (largeSaliencyMap == biggestBlobIdx)
                print biggestBlobPixels.size
                largeSaliencyMap[ biggestBlobPixels ] = self.GC_PR_FGD
                largeSaliencyMap[ biggestBlobPixels == False ] = self.GC_PR_BGD
        
                # Use the largest blob as the segmentation mask
                self.maskArray = largeSaliencyMap
                self.redrawImageWithMask()
            
    #---------------------------------------------------------------------------
    def onComboBrushTypeChanged( self, widget ):
        self.makeBrush()
        
    #---------------------------------------------------------------------------
    def onAdjBrushSizeValueChanged( self, widget ):
        self.makeBrush()
    
    #---------------------------------------------------------------------------
    def onDwgImageButtonPressEvent( self, widget, data ):
        
        if data.button == 1:
            self.onImageMaskChanged( widget, data, self.getCurPixelClass() )
        else:
            self.onImageMaskChanged( widget, data, self.GC_PR_BGD )
            
    #---------------------------------------------------------------------------
    def onDwgImageMotionNotifyEvent( self, widget, data ):
        
        self.onImageMaskChanged( widget, data, self.getCurPixelClass() )
        
    #---------------------------------------------------------------------------
    def onImageMaskChanged( self, widget, data, pixelClass ):
        
        imgRect = self.dwgImageDisplay.getImageRectangleInWidget( widget )
        if imgRect != None:
        
            x = data.x - imgRect.x
            y = data.y - imgRect.y
            self.alterMask( x, y, pixelClass )
    
    #---------------------------------------------------------------------------
    def onDwgImageExposeEvent( self, widget, data ):
        
        imgRect = self.dwgImageDisplay.drawPixBufToDrawingArea( data.area )
        
        if imgRect != None:
            
            imgRect = imgRect.intersect( data.area )
            
            # Add in the mask
            #if self.maskArray != None:
                #self.maskArrayRGB.fill( 0 )
                #self.maskArrayRGB[ self.maskArray == self.GC_FGD ] = self.FOREGROUND_BRUSH_COLOUR
                
                #self.drawingArea.window.draw_pixbuf( 
                    #self.drawingArea.get_style().fg_gc[ gtk.STATE_NORMAL ],
                    #self.pixBuf, srcX, srcY, 
                    #redrawRect.x, redrawRect.y, redrawRect.width, redrawRect.height )
              
            # Draw an overlay to show the selected segmentation
            #if self.markerBuffer != None:
                    
                #graphicsContext = widget.window.new_gc()
                #graphicsContext.set_rgb_fg_color( gtk.gdk.Color( 65535, 65535, 0 ) )
                
                #blockY = imgRect.y
                #for y in range( self.markerBuffer.shape[ 0 ] ):
                
                    #blockX = imgRect.x
                    #for x in range( self.markerBuffer.shape[ 1 ] ):
                        
                        #if self.markerBuffer[ y, x ]:
                            #points = [ (blockX+int((i*2)%self.opticalFlowBlockWidth), blockY+2*int((i*2)/self.opticalFlowBlockWidth)) \
                                #for i in range( int(self.opticalFlowBlockWidth*self.opticalFlowBlockHeight/4) ) ]
                                
                            #widget.window.draw_points( graphicsContext, points )
                            
                        #blockX += self.opticalFlowBlockWidth
                        
                    #blockY += self.opticalFlowBlockHeight

    #---------------------------------------------------------------------------
    def onDwgSegmentationExposeEvent( self, widget, data = None ):
        
        self.dwgSegmentationDisplay.drawPixBufToDrawingArea( data.area )   
        
    #---------------------------------------------------------------------------
    def onDwgSaliencyExposeEvent( self, widget, data = None ):
        
        self.dwgSaliencyDisplay.drawPixBufToDrawingArea( data.area )   

    #---------------------------------------------------------------------------
    def update( self ):

        lastTime = time.clock()

        while 1:
            
            curTime = time.clock()
            
                
            yield True
            
        yield False
        
        
#-------------------------------------------------------------------------------
if __name__ == "__main__":

    mainWindow = MainWindow()
    mainWindow.main()
