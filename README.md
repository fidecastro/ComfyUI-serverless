# ComfyUI-serverless
_**A connector to use ComfyUI in serverless deployments**_

ComfyUI is incredibly flexible and fast; it is the perfect tool launch new workflows in serverless deployments. Unfortunately, there isn't a lot on API documentation and the examples that have been offered so far don't deal with some important issues (for example: good ways to pass images to Comfy, generalized handling of API json files, etc).

Using the websocket endpoint that Comfy offers, I created a very simple way to generate images from Comfy via code. With the ComfyConnector class, you may:

1. Automatically start Comfy webserver (no need to python3 main.py)
2. Easily edit the API json file using the replace_key_value method, regardless of how complex/spaghettized your workflow may be (no need to hardcode your inputs based on each workflow; just tell the function what parameter to look for and it will change it for you)
3. Send to Comfy the API json file containing the workflow topology and editable parameters, and receive back the generated images as an image list object
4. Send to Comfy images and receive back an image list object for use in img2img/controlnet workflows
5. Automatic discovery of the outputs in a JSON file via the find_output_node method
6. Kill main.py after generation using the kill_api method

With this repository, generating images with Comfy takes two lines of code:

    prompt = json.load(open('workflow_api.json'))  # loads the workflow_api.json file as exported by ComfyUI dev mode
    images = api_singleton.generate_images(prompt) # sends the json file and receives back the generated images

This repository makes it very simple to connect ComfyUI with handling functions. It is a drop-in addition to the repository and only interacts with the existing codebase as it extends the utility of its already-functioning websocket API service.

(IMPORTANT: Your workflow MUST CONTAIN one, and only one, SaveImage node for the connector to work, since this will be deemed your output node and will be used by the connector to fetch any generated images.)


