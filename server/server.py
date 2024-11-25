import threading
import os
import re
import subprocess
import json
import logging
import time
import sys

from typing import Any
from lsprotocol.types import (
    INITIALIZED,
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_DID_CLOSE,
    TEXT_DOCUMENT_DID_SAVE,
    DidOpenTextDocumentParams,
    DidChangeTextDocumentParams,
    DidCloseTextDocumentParams,
    Diagnostic,
    TextDocumentItem,
    DiagnosticSeverity,
    PublishDiagnosticsParams,
    Range,
    Position,
)
from pygls.lsp.server import LanguageServer
from urllib.parse import unquote, urlparse

LOG_FILE = os.path.join(os.path.dirname(sys.argv[1]), "lsp.log")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

class HelixLanguageServer(LanguageServer):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.diagnostics = {}

    def parse(self, document: TextDocumentItem):
        diagnostics = []
        uri_path = urlparse(document.uri).path
        decoded_path = unquote(uri_path)  # Decode the URI (removes %3A and similar)
        file_path = os.path.abspath(decoded_path.lstrip('/'))  # Remove leading slash
        
        logging.info("parse called")
        try:
            helix_path = sys.argv[1]
            
            if not os.path.exists(helix_path):
                raise FileNotFoundError(f"Helix binary does not exist: {helix_path}")

            command = [helix_path, file_path, "--lsp-mode"]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()

            if stderr:
                logging.error(f"Helix stderr: {stderr.decode('utf-8')}")

            result = stdout.decode('utf-8')

            ansi_escape_pattern = re.compile(
                r'(?:\x1b|\033|\\001b|\u001b)'  # Matches ESC sequences: \x1b, \033, \u001b, or \001b
                r'(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])'  # Matches the rest of the ANSI escape sequence
            )

            def remove_all_unicode_colors(text):
                return ansi_escape_pattern.sub('', text)
            
            result = remove_all_unicode_colors(result).strip()

            if not result or process.returncode == 0:
                self.diagnostics[document.uri] = (document.version, [])

            logging.debug(f"Helix stdout: {result}")
            json_result = json.loads(result)

            for error in json_result["error"]["errors"]:
                diagnostics.append(
                    Diagnostic(
                        message=error["msg"],
                        severity={
                            "error": DiagnosticSeverity.Error,
                            "note": DiagnosticSeverity.Hint,
                            "warn": DiagnosticSeverity.Warning,
                            "fatal": DiagnosticSeverity.Error,
                        }[str(error["level"]).strip()],
                        range=Range(
                            start=Position(
                                line=int(error["line"])-1,
                                character=int(error["col"])
                            ),
                            end=Position(
                                line=int(error["line"])-1,
                                character=(int(error["col"]) + int(error["offset"]))
                            )
                        ),
                    )
                )

            # Update the diagnostics dictionary with new diagnostics
            self.diagnostics[document.uri] = (document.version, diagnostics)
        except Exception as e:
            logging.error(f"Unexpected error in parse: {e}")
        return diagnostics


SERVER = HelixLanguageServer("HelixLSP", "1.0")


@SERVER.feature(INITIALIZED)
def on_initialized(server: HelixLanguageServer, params):
    logging.info("Server initialized successfully.")
    # add setup logic here to figure out things like config.toml etc...


@SERVER.feature(TEXT_DOCUMENT_DID_OPEN)
def did_open(server: HelixLanguageServer, params: DidOpenTextDocumentParams):
    logging.info(f"Handling 'didOpen' for {params.text_document.uri}")

    doc = server.workspace.get_text_document(params.text_document.uri)
    server.parse(doc)
    
    send_diagnostics(server, params.text_document.uri)

@SERVER.feature(TEXT_DOCUMENT_DID_CLOSE)
def did_close(server: HelixLanguageServer, params: DidCloseTextDocumentParams):
    logging.info(f"Handling 'didClose' for {params.text_document.uri}")
    
    if params.text_document.uri in server.diagnostics:
        del server.diagnostics[params.text_document.uri]
    
    send_diagnostics(server, params.text_document.uri)

@SERVER.feature(TEXT_DOCUMENT_DID_SAVE)
def did_save(server: HelixLanguageServer, params: DidChangeTextDocumentParams):
    logging.info(f"Handling 'didSave' for {params.text_document.uri}")
    
    doc = server.workspace.get_text_document(params.text_document.uri)
    server.parse(doc)
    
    send_diagnostics(server, params.text_document.uri)


def send_diagnostics(server: HelixLanguageServer, uri: str):
    logging.debug(f"Sending diagnostics for {uri}: {server.diagnostics[uri]}")
    
    for _uri, (version, diagnostics) in server.diagnostics.items():
        server.text_document_publish_diagnostics(
            PublishDiagnosticsParams(
                uri=_uri,
                version=version,
                diagnostics=diagnostics,
            )
        )

    server.diagnostics.clear()


if __name__ == "__main__":
    logging.info("Starting Helix Language Server")
    try:
        SERVER.start_io()
    except Exception as e:
        logging.critical(f"Server crashed: {e}")
