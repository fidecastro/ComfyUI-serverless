
import uuid
import json
import urllib.request
import urllib.parse
from PIL import Image
from websocket import WebSocket # note: websocket-client (https://github.com/websocket-client/websocket-client)
import io
import requests
import time
import os
import subprocess
from typing import List
import sys

APP_NAME = os.getenv('APP_NAME') # Name of the application
API_COMMAND_LINE = os.getenv('API_COMMAND_LINE') # Command line to start the API server, e.g. "python3 ComfyUI/main.py"; warning: do not add parameter --port as it will be passed later
API_URL = os.getenv('API_URL')  # URL of the API server (warning: do not add the port number to the URL as it will be passed later)
INITIAL_PORT = int(os.getenv('INITIAL_PORT')) # Initial port to use when starting the API server; may be changed if the port is already in use
INSTANCE_IDENTIFIER = APP_NAME+'-'+str(uuid.uuid4()) # Unique identifier for this instance of the worker
TEST_PAYLOAD = json.load(open(os.getenv('TEST_PAYLOAD'))) # The TEST_PAYLOAD is a JSON object that contains a prompt that will be used to test if the API server is running
MAX_COMFY_START_ATTEMPTS = 10  # Set this to the maximum number of connection attempts to ComfyUI you want

class ComfyConnector:
    _instance = None
    _process = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ComfyConnector, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.urlport = self.find_available_port()
            self.server_address = f"http://{API_URL}:{self.urlport}"
            self.client_id = INSTANCE_IDENTIFIER
            self.ws_address = f"ws://{API_URL}:{self.urlport}/ws?clientId={self.client_id}"
            self.ws = WebSocket()
            self.start_api()
            self.initialized = True

    def find_available_port(self): # If the initial port is already in use, this method finds an available port to start the API server on
        port = INITIAL_PORT
        while True:
            try:
                response = requests.get(f'http://{API_URL}:{port}')
                if response.status_code != 200:
                    return port
                else:
                    port += 1
            except requests.ConnectionError:
                return port
    
    def start_api(self): # This method is used to start the API server
        if not self.is_api_running(): # Block execution until the API server is running
            api_command_line = API_COMMAND_LINE + f" --port {self.urlport}" # Add the port to the command line
            if self._process is None or self._process.poll() is not None: # Check if the process is not running or has terminated for some reason
                self._process = subprocess.Popen(api_command_line.split())
                print("API process started with PID:", self._process.pid)
                attempts = 0
                while not self.is_api_running(): # Block execution until the API server is running
                    if attempts >= MAX_COMFY_START_ATTEMPTS:
                        raise RuntimeError(f"API startup procedure failed after {attempts} attempts.")
                    time.sleep(1)  # Wait for 1 second before checking again
                    attempts += 1 # Increment the number of attempts
                print(f"API startup procedure finalized after {attempts} attempts with PID {self._process.pid} in port {self.urlport}")
                time.sleep(0.5)  # Wait for 0.5 seconds before returning

    def is_api_running(self): # This method is used to check if the API server is running
        test_payload = TEST_PAYLOAD
        try:
            print(f"Checking web server is running in {self.server_address}...")
            response = requests.get(self.server_address)
            if response.status_code == 200: # Check if the API server tells us it's running by returning a 200 status code
                self.ws.connect(self.ws_address)
                print(f"Web server is running (status code 200). Now trying test image...")
                test_image = self.generate_images(test_payload)
                print(f"Type of test_image: {type(test_image)}")
                print(f"Test image: {test_image}")
                if test_image is not None:  # this ensures that the API server is actually running and not just the web server
                    return True
                return False
        except Exception as e:
            print("API not running:", e)
            return False

    def kill_api(self): # This method is used to kill the API server
        if self._process is not None and self._process.poll() is None:
            self._process.kill()
            self._process = None
            print("API process killed")

    def get_history(self, prompt_id): # This method is used to retrieve the history of a prompt from the API server
        with urllib.request.urlopen(f"{self.server_address}/history/{prompt_id}") as response:
            return json.loads(response.read())

    def get_image(self, filename, subfolder, folder_type): # This method is used to retrieve an image from the API server
        data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        url_values = urllib.parse.urlencode(data)
        with urllib.request.urlopen(f"{self.server_address}/view?{url_values}") as response:
            return response.read()

    def queue_prompt(self, prompt): # This method is used to queue a prompt for execution
        p = {"prompt": prompt, "client_id": self.client_id}
        data = json.dumps(p).encode('utf-8')
        headers = {'Content-Type': 'application/json'}  # Set Content-Type header
        req = urllib.request.Request(f"{self.server_address}/prompt", data=data, headers=headers)
        return json.loads(urllib.request.urlopen(req).read())

    def generate_images(self, payload): # This method is used to generate images from a prompt and is the main method of this class
        try:
            if not self.ws.connected: # Check if the WebSocket is connected to the API server and reconnect if necessary
                print("WebSocket is not connected. Reconnecting...")
                self.ws.connect(self.ws_address)
            prompt_id = self.queue_prompt(payload)['prompt_id']
            while True:
                out = self.ws.recv() # Wait for a message from the API server
                if isinstance(out, str): # Check if the message is a string
                    message = json.loads(out) # Parse the message as JSON
                    if message['type'] == 'executing': # Check if the message is an 'executing' message
                        data = message['data'] # Extract the data from the message
                        if data['node'] is None and data['prompt_id'] == prompt_id:
                            break
            address = self.find_output_node(payload) # Find the SaveImage node; workflow MUST contain only one SaveImage node
            history = self.get_history(prompt_id)[prompt_id]
            filenames = eval(f"history['outputs']{address}")['images']  # Extract all images
            images = []
            for img_info in filenames:
                filename = img_info['filename']
                subfolder = img_info['subfolder']
                folder_type = img_info['type']
                image_data = self.get_image(filename, subfolder, folder_type)
                image_file = io.BytesIO(image_data)
                image = Image.open(image_file)
                images.append(image)
            return images
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            line_no = exc_traceback.tb_lineno
            error_message = f'Unhandled error at line {line_no}: {str(e)}'
            print("generate_images - ", error_message)


    def upload_image(self, filepath, subfolder=None, folder_type=None, overwrite=False): # This method is used to upload an image to the API server for use in img2img or controlnet
        try: 
            url = f"{self.server_address}/upload/image"
            files = {'image': open(filepath, 'rb')}
            data = {
                'overwrite': str(overwrite).lower()
            }
            if subfolder:
                data['subfolder'] = subfolder
            if folder_type:
                data['type'] = folder_type
            response = requests.post(url, files=files, data=data)
            return response.json()
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            line_no = exc_traceback.tb_lineno
            error_message = f'upload_image - Unhandled error at line {line_no}: {str(e)}'

    @staticmethod
    def find_output_node(json_object): # This method is used to find the node containing the SaveImage class in a prompt
        for key, value in json_object.items():
            if isinstance(value, dict):
                if value.get("class_type") == "SaveImage":
                    return f"['{key}']"  # Return the key containing the SaveImage class
                result = ComfyConnector.find_output_node(value)
                if result:
                    return result
        return None
    
    @staticmethod
    def load_payload(path):
        with open(path, 'r') as file:
            return json.load(file)

    @staticmethod
    def replace_key_value(json_object, target_key, new_value, class_type_list=None, exclude=True): # This method is used to edit the payload of a prompt
        for key, value in json_object.items():
            # Check if the current value is a dictionary and apply the logic recursively
            if isinstance(value, dict):
                class_type = value.get('class_type')                
                # Determine whether to apply the logic based on exclude and class_type_list
                should_apply_logic = (
                    (exclude and (class_type_list is None or class_type not in class_type_list)) or
                    (not exclude and (class_type_list is not None and class_type in class_type_list))
                )
                # Apply the logic to replace the target key with the new value if conditions are met
                if should_apply_logic and target_key in value:
                    value[target_key] = new_value
                # Recurse vertically (into nested dictionaries)
                ComfyConnector.replace_key_value(value, target_key, new_value, class_type_list, exclude)
            # Recurse sideways (into lists)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        ComfyConnector.replace_key_value(item, target_key, new_value, class_type_list, exclude)
