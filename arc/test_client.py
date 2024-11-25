import socket
import json
from lsprotocol import types

def send_message(sock, message):
    message_str = json.dumps(message)
    message_len = len(message_str)
    sock.sendall(f'Content-Length: {message_len}\r\n\r\n{message_str}'.encode('utf-8'))

def start_lsp_client():
    port = 0
    json_data = json.loads(open("config.json", "r").read())
    port = json_data["port"]
    
    server_address = ('localhost', int(port))  # Use the port your LSP server listens to
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    try:
        sock.connect(server_address)
        
        # Send the initialize message
        initialize_message = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "processId": None,
                "rootUri": "file:///C:/Projects/my-shit/Helix/Helix-lang",
                "capabilities": {},
            }
        }
        send_message(sock, initialize_message)
        
        # Send the didOpen message
        did_open_message = {
            "jsonrpc": "2.0",
            "method": "textDocument/didOpen",
            "params": {
                "textDocument": {
                    "uri": "file:///C:/Projects/my-shit/Helix/Helix-lang/tests/main.hlx",
                    "languageId": "hlx",
                    "version": 1,
                    "text": open("C:/Projects/my-shit/Helix/Helix-lang/tests/main.hlx").read()
                }
            }
        }
        send_message(sock, did_open_message)
        
        # Wait for diagnostics response
        data = sock.recv(4096)
        print(f"Received: {data.decode('utf-8')}")
    
    finally:
        sock.close()

if __name__ == '__main__':
    start_lsp_client()
