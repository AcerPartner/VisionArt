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



class AcerVisionArtNode:
    """
    A example node

    Class methods
    -------------
    INPUT_TYPES (dict):
        Tell the main program input parameters of nodes.
    IS_CHANGED:
        optional method to control when the node is re executed.

    Attributes
    ----------
    RETURN_TYPES (`tuple`):
        The type of each element in the output tuple.
    RETURN_NAMES (`tuple`):
        Optional: The name of each output in the output tuple.
    FUNCTION (`str`):
        The name of the entry-point method. For example, if `FUNCTION = "execute"` then it will run Example().execute()
    OUTPUT_NODE ([`bool`]):
        If this node is an output node that outputs a result/image from the graph. The SaveImage node is an example.
        The backend iterates on these output nodes and tries to execute all their parents if their parent graph is properly connected.
        Assumed to be False if not present.
    CATEGORY (`str`):
        The category the node should appear in the UI.
    DEPRECATED (`bool`):
        Indicates whether the node is deprecated. Deprecated nodes are hidden by default in the UI, but remain
        functional in existing workflows that use them.
    EXPERIMENTAL (`bool`):
        Indicates whether the node is experimental. Experimental nodes are marked as such in the UI and may be subject to
        significant changes or removal in future versions. Use with caution in production workflows.
    execute(s) -> tuple || None:
        The entry point method. The name of this method must be the same as the value of property `FUNCTION`.
        For example, if `FUNCTION = "execute"` then this method's name must be `execute`, if `FUNCTION = "foo"` then it must be `foo`.
    """

    def Command_receive(self, sock, signal):
        logging.info("Command receive listen")
        while signal:
            try:
                data = sock.recv(1024)
                #logging.info("Command Received: ", data.decode('utf-8'))
                # parsing message
                #self.VisionArt_inference_event.set()
            except:
                signal = False
                break
    
    def File_receive(self, sock, signal):
        logging.info("File receive listen")
        while signal:
            try:
                data = sock.recv(1024)
                logging.info("File Received: ", data.decode('utf-8'))
            except:
                signal = False
                break

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        """
            Return a dictionary which contains config for all input fields.
            Some types (string): "MODEL", "VAE", "CLIP", "CONDITIONING", "LATENT", "IMAGE", "INT", "STRING", "FLOAT".
            Input types "INT", "STRING" or "FLOAT" are special values for fields on the node.
            The type can be a list for selection.

            Returns: `dict`:
                - Key input_fields_group (`string`): Can be either required, hidden or optional. A node class must have property `required`
                - Value input_fields (`dict`): Contains input fields config:
                    * Key field_name (`string`): Name of a entry-point method's argument
                    * Value field_config (`tuple`):
                        + First value is a string indicate the type of field or a list for selection.
                        + Second value is a config for type "INT", "STRING" or "FLOAT".
        """
        return {
            "required": {
                "image": ("IMAGE",{"tooltip": "Outpaint 4K image."}),
                #"filename_prefix": ("STRING", {"default": "VisionArt", "tooltip": "The prefix for the file to save. This may include formatting information such as %date:yyyy-MM-dd% or %Empty Latent Image.width% to include values from nodes."}),                
            },
            "hidden": {
                "prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"
            },
        }

    RETURN_TYPES = ()
    OUTPUT_NODE = True

    FUNCTION = "VisionArt"

    CATEGORY = "api/image"
    DESCRIPTION = "Outpaints the input images to desktop wallpaper."

    def VisionArt(self, image, filename_prefix="VisionArt", prompt=None, extra_pnginfo=None):
        logging.info("VisionArt Node!!!!!!!!!")
        # for computex 2025 demo
        # receive image
        for (batch_number, _image) in enumerate(image):
            i = 255. * _image.cpu().numpy()
            img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
            
            # resize image
            resizeImage = img.resize((960,512))
            # save IntelAIPlayground.jpg
            resizeImage.save('C://ProgramData//Acer//AICO//data//IntelAIPlayground.jpg')        

        """
        # call visionart
        # load the user32.dll
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        # Define required constants
        WM_AIPLAYGROUND_VISIONART_START = (0x0400 + 8)
        # Find the window handle (HWND) by window title
        hwnd = user32.FindWindowW(None, "AICOOutPaintingAPP")  # Example: Notepad
        if hwnd:
            #Send windows event start outpainting
            user32.PostMessageW(hwnd, WM_AIPLAYGROUND_VISIONART_START, 0, 0)
        """
        # AICO 2.0 protocol
        logging.info("Acer VisionArt socket connect begin.")
        HOST = '127.0.0.1'
        commandPort = 46936
        filePort = 46937
        commandSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        fileSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try: 
            commandSocket.connect((HOST, commandPort))
            logging.info("command socket connect success.")
            fileSocket.connect((HOST, filePort))
            logging.info("file socket connect success.")            
        except ConnectionRefusedError:
            logging.info("command Acer VisionArt Connect fail.")


        logging.info("Command receive thread start.")
        # start receive and listen
        receiveThread = threading.Thread(target = self.Command_receive, args = (commandSocket, True))
        receiveThread.start()
        logging.info("File receive thread start.")
        # start receive and listen
        receiveThread = threading.Thread(target = self.File_receive, args = (fileSocket, True))
        receiveThread.start()

        local_command_ip, local_command_port = commandSocket.getsockname()
        logging.info("client command IP: {}, Port: {}".format(local_command_ip, local_command_port))
        local_file_ip, local_file_port = fileSocket.getsockname()
        logging.info("client file IP: {}, Port: {}".format(local_file_ip, local_file_port))

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

        # file socket format
        str_aico_registry = json.dumps(aico_registry)
        cmdSize = len(str_aico_registry.encode('utf-8'))
        logging.info("file socket command size: "+ str(cmdSize) )   #167/ a7
        byte_cmdSize = cmdSize.to_bytes(8, 'little')
        print("byte cmdSize: ", byte_cmdSize)

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
        
        time.sleep(5)
        logging.info("AICO_EXECUTED begin.")
        
        magicWord = "ACER"
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
                "outpaint_animation": 1,
                "outpaint_animation_speed": 20,
                "outpaint_inference_step": 20, 
                "seed": 0,
                "outpaint_inference_seed": 0,
                "outpaint_performance": 1,
                "outpaint_input_image": 1,
                "outpaint_prompts": "one small cute French Bulldog, smiling camera zoom out entire face of puppy,looking at camera, face at center image, photo realistic, undistorted, 8k, undistorted, cuddly, lively, outdoor "
            }
        }
        aico_executed_registry = json.dumps(aico_executed)
        cmdSize = len(aico_executed_registry.encode('utf-8'))
        logging.info("file socket command size: "+ str(cmdSize) ) 
        byte_cmdSize = cmdSize.to_bytes(8, 'little')
        print("byte cmdSize: ", byte_cmdSize)

        # image to byte buffer 
        byte_buffer = io.BytesIO()
        resizeImage.save(byte_buffer, format="JPEG")
        bytes_image = byte_buffer.getvalue()
        imageSize = len(bytes_image)
        byte_imageSize = imageSize.to_bytes(8, 'little')

        message = magicWord.encode('utf-8') + byte_cmdID + byte_cmdSize + json.dumps(aico_executed).encode('utf-8')+ byte_imageSize + bytes_image
        
        try:
            fileSocket.sendall(message)
            logging.info("send AICO_EXECUTED success.")
        except:
            logging.info("send AICO_EXECUTED fail.")
        
        return (image,)
        #return { "ui": { "images": True } }

# A dictionary that contains all nodes you want to export with their names
# NOTE: names should be globally unique
NODE_CLASS_MAPPINGS = {
    "Acer": AcerVisionArtNode
}

# A dictionary that contains the friendly/humanly readable titles for the nodes
NODE_DISPLAY_NAME_MAPPINGS = {
    "Acer": "VisionArt Node"
}
