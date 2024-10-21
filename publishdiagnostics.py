import os
import threading
import time
from lsprotocol import types
import json
import subprocess
import logging
from pygls.lsp.server import LanguageServer
from urllib.parse import unquote, urlparse


def async_print(level, message):
    # 1: Error, 2: Warning, 3: Info, 4: Debug
    if level == 1:
        logging.error(message)
    elif level == 2:
        logging.warning(message)
    elif level == 3:
        logging.info(message)
    elif level == 4:
        logging.debug(message)
    else:
        logging.info(message)

class PublishDiagnosticServer(LanguageServer):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(message)s')
        async_print(4, "Server initialized")
        self.diagnostics = {}

    def parse(self, document: types.TextDocumentItem):
        diagnostics = []
        uri_path = urlparse(document.uri).path
        decoded_path = unquote(uri_path)  # Decode the URI (removes %3A and similar)
        file_path = os.path.abspath(decoded_path.lstrip('/'))  # Remove leading slash
        
        try:
            async_print(4, f"Parsing document: {document.uri}")
            helix_path = json.loads(open("config.json", "r").read())["helix_path"]
            if not helix_path:
                raise Exception("Helix path not set in config.json")
            if not os.path.exists(helix_path):
                raise Exception("Helix path does not exist")
            command = [helix_path, file_path, "--lsp-mode"]
            async_print(4, f"Running command: {command}")
            
            process: subprocess.Popen = subprocess.Popen(
                command, 
                stdout=subprocess.PIPE
            )
            result: str = process.communicate()[0].decode("utf-8")
            exit_code: int = process.returncode
            async_print(4, f"Result from helix: {result}, Exit code: {exit_code}")

            if exit_code:
                if result:
                    json_result = json.loads(result.strip())
                    async_print(4, f"Parsed JSON result: {json_result}")
                    
                    if "error_type" in json_result and json_result["error_type"] == "code":
                        diagnostics.append(
                            types.Diagnostic(
                                message=json_result["msg"],
                                severity={
                                    "error": types.DiagnosticSeverity.Error,
                                    "note": types.DiagnosticSeverity.Hint,
                                    "warn": types.DiagnosticSeverity.Warning,
                                    "fatal": types.DiagnosticSeverity.Error,
                                }[str(json_result["level"]).strip()],
                                range=types.Range(
                                    start=types.Position(
                                        line=int(json_result["line"])-1,
                                        character=json_result["col"]
                                    ),
                                    end=types.Position(
                                        line=int(json_result["line"])-1,
                                        character=(json_result["col"] + json_result["offset"])
                                    )
                                ),
                            )
                        )

            # Update the diagnostics dictionary with new diagnostics
            self.diagnostics[document.uri] = (document.version, diagnostics)

        except Exception as e:
            logging.error(f"Error parsing document: {e}")
            raise e

                    
HelixLanguageServer = PublishDiagnosticServer("diag", "v0.1")

@HelixLanguageServer.feature(types.TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: PublishDiagnosticServer, params: types.DidOpenTextDocumentParams):
    doc = ls.workspace.get_text_document(params.text_document.uri)
    
    # Parse the document and update diagnostics
    ls.parse(doc)
    
    # Send diagnostics to the client
    for uri, (version, diagnostics) in ls.diagnostics.items():
        ls.text_document_publish_diagnostics(
            types.PublishDiagnosticsParams(
                uri=uri,
                version=version,
                diagnostics=diagnostics,
            )
        )


@HelixLanguageServer.feature(types.TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: PublishDiagnosticServer, params: types.DidChangeTextDocumentParams):
    doc = ls.workspace.get_text_document(params.text_document.uri)
    
    # First pass: parse the document for diagnostics
    ls.parse(doc)  # Trigger initial parsing

    # Send diagnostics after the first parse
    send_diagnostics(ls, doc.uri)

    # Second pass: rerun the diagnostics with a delay
    def delayed_parse():
        time.sleep(0.5)  # Delay by 500 milliseconds
        ls.parse(doc)  # Re-run the parsing
        send_diagnostics(ls, doc.uri)  # Send diagnostics again after the second parse

    threading.Thread(target=delayed_parse).start()


def send_diagnostics(ls, uri):
    """Helper function to send diagnostics for a document."""
    if uri in ls.diagnostics:
        version, diagnostics = ls.diagnostics[uri]
        ls.text_document_publish_diagnostics(
            types.PublishDiagnosticsParams(
                uri=uri,
                version=version,
                diagnostics=diagnostics,
            )
        )

def save_port_info(server_ptr: list[HelixLanguageServer]): # type: ignore
    time.sleep(1)  # Wait for server to start
    
    actual_port = server_ptr[0]._server.sockets[0].getsockname()[1]
    
    # write the key to congig.json
    
    json_data = json.loads(open("config.json", "r").read())
    json_data["port"] = actual_port
    
    with open("config.json", "w") as f:
        f.write(json.dumps(json_data, indent=4))

if __name__ == '__main__':
    server = HelixLanguageServer
    
    host = '127.0.0.1'
    port = 0  # Let OS pick a free port
    
    server_ptr = [server, 0]
    thread = threading.Thread(target=save_port_info, args=(server_ptr,), daemon=True)
    thread.start()
    
    server.start_tcp(host, port)