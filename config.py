# this gets the python path and the helix path and sets up a .vscode/settings.json

import os
import json
import sys

def get_py_path():
    return sys.executable

def get_helix_path():
    return input("Enter the path to the helix binary:\n>>> ")

def get_server_path():
    return os.path.join(os.path.dirname(__file__), "server", "server.py")

def write_settings():
    settings = {}

    settings["helix.path"]       = get_helix_path()
    settings["helix.pythonPath"] = get_py_path()
    settings["helix.serverPath"] = get_server_path()

    # print the json to the console
    print(json.dumps(settings, indent=4))

if __name__ == "__main__":
    write_settings()
