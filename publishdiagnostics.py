import os
import threading
import time
from lsprotocol import types
import json
import subprocess
import logging
from pygls.lsp.server import LanguageServer
from urllib.parse import urlparse


class PublishDiagnosticServer(LanguageServer):

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(message)s')
        logging.debug("Server initialized")
        self.diagnostics = {}

    def parse(self, document: types.TextDocumentItem):
        diagnostics = []
        uri_path = urlparse(document.uri).path
        file_path = os.path.abspath(uri_path)
        try:
            logging.debug(f"Parsing document: {document.uri}")
            process: subprocess.Popen = subprocess.Popen(
                ["C:/Projects/my-shit/helix/helix-lang/build/release/x64-msvc-windows/bin/helix.exe", file_path, "--lsp-mode"], stdout=subprocess.PIPE
            )
            result: str = process.communicate()[0].decode("utf-8")
            exit_code: int = process.returncode
            logging.debug(f"Result from helix: {result}, Exit code: {exit_code}")

            if exit_code:
                if result:
                    json_result = json.loads(result)
                    logging.debug(f"Parsed JSON result: {json_result}")
                    if json_result["error_type"] == "code":
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
                                        line=json_result["line"],
                                        character=json_result["col"]
                                    ),
                                    end=types.Position(
                                        line=json_result["line"],
                                        character=(json_result["col"] + json_result["offset"])
                                    )
                                ),
                            )
                        )
            self.diagnostics[document.uri] = (document.version, diagnostics)
        except Exception as e:
            logging.error(f"Error parsing document: {e}")
            raise e
                    
HelixLanguageServer = PublishDiagnosticServer("diag", "v0.1")

@HelixLanguageServer.feature(types.TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: PublishDiagnosticServer, params: types.DidOpenTextDocumentParams):
    doc = ls.workspace.get_text_document(params.text_document.uri)
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
    for uri, (version, diagnostics) in ls.diagnostics.items():
        ls.text_document_publish_diagnostics(
            types.PublishDiagnosticsParams(
                uri=uri,
                version=version,
                diagnostics=diagnostics,
            )
        )

def save_port_info(server_ptr: list[HelixLanguageServer]):
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