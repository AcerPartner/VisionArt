import os
import sys
import json
import logging
import threading
import time
import io

import importlib.util
from PIL import Image, ImageOps, ImageSequence
from PIL.PngImagePlugin import PngInfo
import numpy as np

# socket
import socket
# json
import json
from datetime import datetime

# visionart
import ctypes
from ctypes import wintypes

import folder_paths

command_event = threading.Event()
file_event = threading.Event()

commandSocketFlag = {'run': True}
fileSocketFlag = {'run': True}

local_command_ip = 1234
local_command_port = 1234
local_file_ip = 1234 
local_file_port = 1234

img_resizeImage = None

byte_resizeImageBuffer = bytearray()
byte_VisionArtImageBuffer = bytearray()

class AcerSaveImage:
    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        self.type = "output"
        self.prefix_append = ""
        self.compress_level = 4
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "The images to save."}),
                "filename_prefix": ("STRING", {"default": "AcerVisionArt", "tooltip": "The prefix for the file to save. This may include formatting information such as %date:yyyy-MM-dd% or %Empty Latent Image.width% to include values from nodes."})
            },
            "hidden": {
                "prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"
            },
        }

    RETURN_TYPES = ()
    FUNCTION = "save_images"

    OUTPUT_NODE = True

    CATEGORY = "api/image"
    DESCRIPTION = "Saves the input images to your Acer VisionArt output directory."

    def save_images(self, images, filename_prefix="AcerVisionArt", prompt=None, extra_pnginfo=None):
        full_output_folder, filename, counter, subfolder, filename_prefix = folder_paths.get_save_image_path(filename_prefix, self.output_dir)
        logging.info("full_output_folder: "+ full_output_folder)
        logging.info("filename: "+ filename)
        logging.info("subfolder: "+ subfolder)
        logging.info("filename_prefix: "+ filename_prefix)
        file = f"{filename_prefix}_{counter:05}_.png"
        images.save(os.path.join(full_output_folder, file))
        results = list()

        results.append({
            "filename": file,
            "subfolder": subfolder,
            "type": self.type
        })
        counter += 1
        
        return { "ui": { "images": results } }

class AcerVisionArtNode:
    
    def Command_receive(self, sock, flag):
        logging.info("Command receive listen")
        while commandSocketFlag['run']:
            try:
                receiveData = sock.recv(4096)
                receiveDataSize = len(receiveData)
                subReceiveData = receiveData[8:receiveDataSize]
                json_str = subReceiveData.decode('utf-8')
                responseMessage = json.loads(json_str)
                logging.info("Command Received: " + receiveData.decode('utf-8'))
                # parsing message
                #self.VisionArt_inference_event.set()
            except:
                command_event.set()
                commandSocketFlag['run'] = False 
                break
    
    def File_receive(self, sock, flag):
        logging.info("File receive listen")
        while fileSocketFlag['run']:
            try:
                receiveData = sock.recv(4096)
                # message length
                receiveDataSize = len(receiveData)
                # json message length
                byte_jsonLength = receiveData[8:15]
                jsonLength = int.from_bytes(byte_jsonLength, byteorder='little')
                # get json message
                byte_json = receiveData[15:jsonLength + 15]
                str_json = byte_json.decode('utf-8')
                logging.info("JSON: " + str_json)
                # get image length 
                byte_imageLength = receiveData[jsonLength + 16:jsonLength + 19]
                imageLength = int.from_bytes(byte_imageLength, byteorder='little')

                if imageLength > 10:
                    # get image
                    byte_image = receiveData[jsonLength + 24:receiveDataSize]
                    tempImageLength = imageLength - len(byte_image)
                    while tempImageLength > 0:
                        more = sock.recv(4096)
                        byte_image += more
                        tempImageLength -= len(more)
                    
                    with open('VisionArt_image.png', 'wb') as f:
                        f.write(byte_image)
                    
                    global byte_VisionArtImageBuffer 
                    byte_VisionArtImageBuffer = byte_image
                    command_event.set()
                    file_event.set()
                    fileSocketFlag['run'] = False

            except Exception as e:
                logging.info("VisionArt Error type: " + type(e).__name__)
                logging.info("VisionArt Error message: " + str(e))
                file_event.set()
                fileSocketFlag['run'] = False
                break
    
    def Command_builder(self):
        HOST = '127.0.0.1'
        commandPort = 46936
        filePort = 46937
        commandSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
        try: 
            commandSocket.connect((HOST, commandPort))
            logging.info("command socket connect success.")        
        except ConnectionRefusedError:
            logging.info("command Acer VisionArt Connect fail.")

        # start receive and listen
        receiveThread = threading.Thread(target = self.Command_receive, args = (commandSocket, commandSocketFlag))
        receiveThread.start()

        local_command_ip, local_command_port = commandSocket.getsockname()
        logging.info("client command IP: {}, Port: {}".format(local_command_ip, local_command_port))
    
        # command socket format
        magicWord = "ACER"
        cmdID = 0
        byte_cmdID = cmdID.to_bytes(4, 'little')
        aico_registry = { 
            "Function": "AICO_REGISTRY",
            "Feature": 0,
            "TimeStamp": datetime.now().timestamp(), 
            "Parameter":{ 
                "command_port": local_command_port,
                "file_port": local_file_port,
                "request_feature": 1, 
                "support_feature": 999 
            }
        }
        message = magicWord.encode('utf-8') + byte_cmdID + json.dumps(aico_registry).encode('utf-8')
        try:
            commandSocket.sendall(message)
            logging.info("command socket AICO_REGISTRY success.")
        except:
            logging.info("command socket AICO_REGISTRY fail.")

        logging.info("command socket wait event")
        command_event.wait()
        logging.info("command socket registry finish")
        commandSocketFlag['run'] = False

        aico_rversion = { 
            "Function": "AICO_VERSION",
            "Feature": 0,
            "TimeStamp": datetime.now().timestamp()
        }
        message = magicWord.encode('utf-8') + byte_cmdID + json.dumps(aico_rversion).encode('utf-8')
        try:
            commandSocket.sendall(message)
            logging.info("command socket AICO_VERSION success.")
        except:
            logging.info("command socket AICO_VERSION fail.")

    def File_builder(self, animation_mode, performance_mode):
        HOST = '127.0.0.1'
        commandPort = 46936
        filePort = 46937
        fileSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
        try: 
            fileSocket.connect((HOST, filePort))
            logging.info("file socket connect success.")            
        except ConnectionRefusedError:
            logging.info("file Acer VisionArt Connect fail.")
    
        local_file_ip, local_file_port = fileSocket.getsockname()
        logging.info("client command IP: {}, Port: {}".format(local_file_ip, local_file_port))

        # start receive and listen
        receiveThread = threading.Thread(target = self.File_receive, args = (fileSocket, fileSocketFlag))
        receiveThread.start()

        # file socket format
        magicWord = "ACER"
        cmdID = 0
        byte_cmdID = cmdID.to_bytes(4, 'little')
        aico_registry = { 
            "Function": "AICO_REGISTRY",
            "Feature": 0,
            "TimeStamp": datetime.now().timestamp(), 
            "Parameter":{ 
                "command_port": local_command_port,
                "file_port": local_file_port,
                "request_feature": 1, 
                "support_feature": 999 
            }
        }
        str_aico_registry = json.dumps(aico_registry)
        cmdSize = len(str_aico_registry.encode('utf-8'))
        byte_cmdSize = cmdSize.to_bytes(8, 'little')

        imageSize = 0
        byte_imageSize = imageSize.to_bytes(8, 'little')
        tempBuffer = 1
        byte_temp_buffer = tempBuffer.to_bytes(1, 'little')
        message = magicWord.encode('utf-8') + byte_cmdID + byte_cmdSize + json.dumps(aico_registry).encode('utf-8') + byte_imageSize + byte_temp_buffer
        try:
            fileSocket.sendall(message)
            logging.info("file socket AICO_REGISTRY success.")
        except:
            logging.info("file socket AICO_REGISTRY fail.")

        # EXECUTE 4K Image
        cmdID = 60
        byte_cmdID = cmdID.to_bytes(4, 'little')
        aico_executed = {
            "Function": "OUTPAINT_EXECUTED",
            "Feature": 1,
            "TimeStamp":datetime.now().timestamp(),
            "Parameter":{ 
                "outpaint_image_position": 0,
                "outpaint_execute": 0,
                "outpaint_format": 0, 
                "outpaint_animation": animation_mode,                  #0: set wallpaper, 1: animation wallpaper, 2: full screen wallpaper
                "outpaint_animation_speed": 20,
                "outpaint_inference_step": 20, 
                "seed": 0,
                "outpaint_inference_seed": 0,
                "outpaint_performance": performance_mode,              #0: release VisionArt resource, 1: keep VersionArt resource
                "outpaint_input_image": 1,                             #0: VisionArt generate image, 1: VisionArt receive image
                #"outpaint_prompts": "Front view of smiling Scottish Fold cat centered in the image, 8k, Realistic cat, Beach is in the background, big round pupils, big round eyes, big round eyeballs, undistorted, small size, photorealistic, cuddly, Vibrant colors, Rich details, Ultra-quality"                                 #outpaint_input_image= 0: using prompts generate image, outpaint_input_image= 1: Unused.
            }
        }

        aico_executed_registry = json.dumps(aico_executed)
        cmdSize = len(aico_executed_registry.encode('utf-8'))
        logging.info("file socket command size: "+ str(cmdSize) ) 
        byte_cmdSize = cmdSize.to_bytes(8, 'little')
        # image to byte buffer 
        byte_buffer = io.BytesIO()
        global img_resizeImage
        img_resizeImage.save(byte_buffer, format="JPEG")
        bytes_image = byte_buffer.getvalue()
        imageSize = len(bytes_image)
        byte_imageSize = imageSize.to_bytes(8, 'little')
        logging.info("image size: " + str(imageSize))

        message = magicWord.encode('utf-8') + byte_cmdID + byte_cmdSize + json.dumps(aico_executed).encode('utf-8')+ byte_imageSize + bytes_image
        
        try:
            fileSocket.sendall(message)
            logging.info("send AICO_EXECUTED success.")
        except:
            logging.info("send AICO_EXECUTED fail.")
    
        logging.info("Wait VisionArt return 4K image")
        file_event.wait()
        # OUTPAINT_OUTPUT_IMAGE
    
        fileSocketFlag['run'] = False

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        
        return {
            "required": {
                "image": ("IMAGE",{"tooltip": "Outpaint 4K image."}),
                "animation_mode":("INT",{"default": 2, "min": 0, "max": 2, "tooltip": "animation present mode"}), # 0: WALLPAPER, 1: ANIMATION_WALLPAPER, 2: ANIMATION_FULLSCREEN
                "performance_mode":("INT",{"default": 0, "min": 0, "max": 1, "tooltip": "keep VisionArt resource"}), # 0: release resource, 1: keep resource
                #"filename_prefix": ("STRING", {"default": "VisionArt", "tooltip": "The prefix for the file to save. This may include formatting information such as %date:yyyy-MM-dd% or %Empty Latent Image.width% to include values from nodes."}),                
            },
            "hidden": {
                "prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"
            },
        }

    RETURN_TYPES = ("IMAGE",)
    OUTPUT_TOOLTIPS = ("4K image.",)
    OUTPUT_NODE = True

    FUNCTION = "VisionArt"

    CATEGORY = "api/image"
    DESCRIPTION = "Outpaints the input images to desktop wallpaper."

    def VisionArt(self, image, filename_prefix="VisionArt", prompt=None, extra_pnginfo=None, animation_mode=2, performance_mode=0):
        logging.info("VisionArt Node!!!!!!!!!")
        
        # receive image
        for (batch_number, _image) in enumerate(image):
            i = 255. * _image.cpu().numpy()
            img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
            
            # resize image
            global img_resizeImage 
            img_resizeImage = img.resize((960,512))

        commandThread = threading.Thread(target = self.Command_builder,)
        commandThread.start()
        fileThread = threading.Thread(target = self.File_builder, args=(animation_mode, performance_mode))
        fileThread.start()

        commandThread.join()
        fileThread.join()
        logging.info("VisionArt Finish!!!!!!!!!")

        global byte_VisionArtImageBuffer
        image_stream = io.BytesIO(byte_VisionArtImageBuffer)
        image4K = Image.open(image_stream)
        # for debug save image
        # image4K.save('C://ProgramData//Acer//AICO//data//IntelAIPlayground_4K.png')
        # reset to default
        command_event.clear()
        file_event.clear()
        commandSocketFlag['run'] = True
        fileSocketFlag['run'] = True
        return (image4K,)
        

# A dictionary that contains all nodes you want to export with their names
# NOTE: names should be globally unique
NODE_CLASS_MAPPINGS = {
    "Acer": AcerVisionArtNode,
    "AcerSaveImage": AcerSaveImage
}

# A dictionary that contains the friendly/humanly readable titles for the nodes
NODE_DISPLAY_NAME_MAPPINGS = {
    "Acer": "VisionArt Node",
    "AcerSaveImage": "VisionArt SaveImage Node",
}
