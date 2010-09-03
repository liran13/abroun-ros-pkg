
from ros import rosrecord
import numpy as np
import cv
import Utils

import math
import random
import sys
sys.path.append( "../" )
from OpticalFlowFilter import OpticalFlowFilter

#-------------------------------------------------------------------------------
class InputSequence:
    '''A sequence of images and a sequence of servo angles read from a bag file''' 
    
    #---------------------------------------------------------------------------
    def __init__( self, bagFilename ):
        
        self.servoAngleTimes = []
        self.servoAngleData = []
        self.cameraImages = []
        self.imageTimes = []
        
        # Optical flow variables
        self.opticalFlowArraysX = None
        self.opticalFlowArraysY = None
        self.opticalFlowMethod = None
        self.opticalFlowFilter = None
        self.opticalFlowCalculated = False
        
        # Extract messages from the bag
        startTime = None
        lastAngleTime = None
        lastCameraTime = None
        
        for topic, msg, t in rosrecord.logplayer( bagFilename ):
            if startTime == None:
                startTime = t
                
            bagTime = t - startTime
                
            if msg._type == "arm_driver_msgs/SetServoAngles" \
                and bagTime != lastAngleTime:
                
                lastAngleTime = bagTime
                self.servoAngleTimes.append( bagTime.to_sec() )
                
                servoAngle = msg.servoAngles[ 0 ].angle
                self.servoAngleData.append( servoAngle )
                
            elif msg._type == "sensor_msgs/Image" \
                and bagTime != lastCameraTime:

                lastCameraTime = bagTime
                self.imageTimes.append( bagTime.to_sec() )
                
                # Convert the image to a numpy array
                if msg.encoding == "rgb8" or msg.encoding == "bgr8":
            
                    image = np.fromstring( msg.data, dtype=np.uint8 )
                    image.shape = ( msg.height, msg.width, 3 )
                    self.cameraImages.append( image )
            
                else:
                    rospy.logerr( "Unhandled image encoding - " + rosImage.encoding )
                
        self.servoAngleData = Utils.normaliseSequence( self.servoAngleData )
       
    #---------------------------------------------------------------------------
    def addDistractorObjects( self, numDistractorObjects, randomSeed = None ):
        
        DISTRACTOR_RADIUS = 24
        DISTRACTOR_DIM = DISTRACTOR_RADIUS*2 + 1
        i = np.indices( ( DISTRACTOR_DIM, DISTRACTOR_DIM ) ) - DISTRACTOR_RADIUS
        distractorIndices = np.where( i[0]*i[0] + i[1]*i[1] <= DISTRACTOR_RADIUS*DISTRACTOR_RADIUS )
        
        startPos = ( 12, 12 )
        endPos = ( 35, 36 )
        frequency = 0.8
        
        distractorPos = ( 12, 12 )
        
        if randomSeed != None:
            random.seed( randomSeed )
            
        distractorData = np.array( 
            np.random.rand( DISTRACTOR_DIM, DISTRACTOR_DIM )*255, dtype=np.int8 )
        
        # Add the distractors to the image
        for imageIdx, image in enumerate( self.cameraImages ):
            
            time = self.imageTimes[ imageIdx ]
            offset = math.cos( time*frequency*2.0*math.pi )
            offset = (1.0 - offset) / 2.0
            
            if time < 3.5 or time > 7.5:
                continue
            
            posX = int( startPos[ 0 ] + offset*(endPos[ 0 ] - startPos[ 0 ]) )
            posY = int( startPos[ 1 ] + offset*(endPos[ 1 ] - startPos[ 1 ]) )
            
            imageTargetIndices = ( 
                distractorIndices[ 0 ] - DISTRACTOR_RADIUS + posX,
                distractorIndices[ 1 ] - DISTRACTOR_RADIUS + posY )
            image[ imageTargetIndices[ 0 ], imageTargetIndices[ 1 ], 0 ] = distractorData[ distractorIndices ]
            image[ imageTargetIndices[ 0 ], imageTargetIndices[ 1 ], 1 ] = distractorData[ distractorIndices ]
            image[ imageTargetIndices[ 0 ], imageTargetIndices[ 1 ], 2 ] = distractorData[ distractorIndices ]

    #---------------------------------------------------------------------------
    def calculateOpticalFlow( self,
        opticalFlowBlockWidth, opticalFlowBlockHeight, 
        opticalFlowRangeWidth, opticalFlowRangeHeight, opticalFlowMethod ):
          
        numImages = len( self.cameraImages )  
        if numImages <= 0:
            return False  # Nothing to calculate optical flow with
            
        self.opticalFlowMethod = opticalFlowMethod
        self.opticalFlowFilter = OpticalFlowFilter(
            opticalFlowBlockWidth, opticalFlowBlockHeight, 
            opticalFlowRangeWidth, opticalFlowRangeHeight )
        
        # Create arrays to hold the optical flow
        opticalFlowWidth = self.opticalFlowFilter.calcOpticalFlowWidth( self.cameraImages[ 0 ].shape[ 1 ] )
        opticalFlowHeight = self.opticalFlowFilter.calcOpticalFlowHeight( self.cameraImages[ 0 ].shape[ 0 ] )
        opticalFlowArrayShape = ( opticalFlowHeight, opticalFlowWidth, numImages )
        self.opticalFlowArraysX = np.ndarray( shape=opticalFlowArrayShape, dtype=np.float32 )
        self.opticalFlowArraysY = np.ndarray( shape=opticalFlowArrayShape, dtype=np.float32 )

        for imageIdx, image in enumerate( self.cameraImages ):
            opticalFlowArrayX, opticalFlowArrayY = self.processCameraImage( image )
            
            self.opticalFlowArraysX[ :, :, imageIdx ] = np.array( opticalFlowArrayX )
            self.opticalFlowArraysY[ :, :, imageIdx ] = np.array( opticalFlowArrayY )
            
        self.opticalFlowCalculated = True
        return True
            
    #---------------------------------------------------------------------------
    def processCameraImage( self, image ):
        
        opticalFlowArrayX = None
        opticalFlowArrayY = None
        
        # Create an OpenCV image to process the data
        curImageGray = cv.CreateImage( ( image.shape[ 1 ], image.shape[ 0 ] ), cv.IPL_DEPTH_8U, 1 )
        cv.CvtColor( image, curImageGray, cv.CV_RGB2GRAY )
        
        # Look for optical flow between this image and the last one
        opticalFlowArrayX, opticalFlowArrayY = \
            self.opticalFlowFilter.calcOpticalFlow( curImageGray, self.opticalFlowMethod )
            
        return ( opticalFlowArrayX, opticalFlowArrayY )