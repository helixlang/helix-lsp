# this gets the python path and the kairo path and sets up a .vscode/settings.json

import os
import json
import sys

def get_py_path():
    return sys.executable

def get_kairo_path():
    return input("Enter the path to the kairo binary:\n>>> ")

def get_server_path():
    return os.path.join(os.path.dirname(__file__), "server", "server.py")

def write_settings():
    settings = {}

    settings["kairo.path"]       = get_kairo_path()
    settings["kairo.pythonPath"] = get_py_path()
    settings["kairo.serverPath"] = get_server_path()

    # print the json to the console
    print(json.dumps(settings, indent=4))

if __name__ == "__main__":
    write_settings()
