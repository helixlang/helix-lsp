"""Helix Language Server

This file creates and initializes all the LSP features.

"""
import os
import subprocess
import json
import time
from typing import Any
from urllib.parse import (
    unquote,
    urlparse
)
from lsprotocol.types import (
    TEXT_DOCUMENT_DIAGNOSTIC,
    TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_DID_CLOSE,
    TEXT_DOCUMENT_DID_OPEN,
    DidOpenTextDocumentParams,
    DidChangeTextDocumentParams,
    DidCloseTextDocumentParams,
    TextDocumentItem,
    Diagnostic,
    DiagnosticSeverity,
    Range,
    Position,
)
from pygls.lsp.server import LanguageServer
from pygls.uris import to_fs_path as lsp_uri_to_path


class HelixLanguageServer(LanguageServer):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def get_errors(self, document: TextDocumentItem) -> dict:
        diagnostics = []
        uri = document.uri
        file_path = lsp_uri_to_path(uri)

        try:
            helix_path = json.loads(open("config.json", "r").read())[
                "helix_path"]
            
            if not helix_path:
                raise Exception("Helix path not set in config.json")
            if not os.path.exists(helix_path):
                raise Exception("Helix path does not exist")
            command = [helix_path, file_path, "--lsp-mode"]

            process: subprocess.Popen = subprocess.Popen(
                command,
                stdout=subprocess.PIPE
            )
            result: str = process.communicate()[0].decode("utf-8")
            exit_code: int = process.returncode

            if exit_code:
                if result:
                    json_result = json.loads(result.strip())
                    for error in json_result["error"]["errors"]: 
                        diagnostics.append(
                            Diagnostic(
                                message=error["msg"],
                                severity ={
                                    "error": DiagnosticSeverity.Error,
                                    "note" : DiagnosticSeverity.Hint,
                                    "warn" : DiagnosticSeverity.Warning,
                                    "fatal": DiagnosticSeverity.Error,
                                }[str(error["level"]).strip()],
                                range=Range(
                                    start=Position(
                                        line=int(error["line"])-1,
                                        character=error["col"]
                                    ),
                                    end=Position(
                                        line=int(error["line"])-1,
                                        character=(error["col"] + error["offset"])
                                    )
                                ),
                            )
                        )
            return diagnostics
        except Exception as e:
            raise e    
    
    def get_cxir_errors(self, document: TextDocumentItem) -> dict:
        diagnostics = []
        uri = document.uri
        file_path = lsp_uri_to_path(uri)

        try:
            helix_path = json.loads(open("config.json", "r").read())[
                "helix_path"]
            if not helix_path:
                raise Exception("Helix path not set in config.json")
            if not os.path.exists(helix_path):
                raise Exception("Helix path does not exist")
            command = [helix_path, file_path, "--lsp-mode", "--emit-ir"]

            process: subprocess.Popen = subprocess.Popen(
                command,
                stdout=subprocess.PIPE
            )
            result: str = process.communicate()[0].decode("utf-8")
            exit_code: int = process.returncode

            if exit_code:
                if result:
                    json_result = json.loads(result.strip())
                    for error in json_result["error"]["errors"]:
                        if helix_path in error["file"]:
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
                                            character=error["col"]
                                        ),
                                        end=Position(
                                            line=int(error["line"])-1,
                                            character=(error["col"] + error["offset"])
                                        )
                                    ),
                                )
                            )
        except Exception as e:
            raise e

SERVER = HelixLanguageServer(
    name="HelixLSP",
    version="V1"
)


def publish_diagnostics(server: HelixLanguageServer, uri: str) -> None:
    if uri not in server.workspace.document:
        return
    doc = server.workspace.get_text_document(uri)
    diagnostics = server.get_errors(doc)
    if not diagnostics or time.time() - server.workspace.document[uri][1] > 5:
        diagnostics = server.get_cxir_errors(doc)
        
    server.publish_diagnostics(uri, diagnostics)

@SERVER.feature(TEXT_DOCUMENT_DID_CHANGE)
def did_change(
    server: HelixLanguageServer, params: DidChangeTextDocumentParams
) -> None:
    publish_diagnostics(server, params.text_document.uri)


@SERVER.feature(TEXT_DOCUMENT_DID_OPEN)
def did_open(
    server: HelixLanguageServer, params: DidOpenTextDocumentParams
) -> None:
    publish_diagnostics(server, params.text_document.uri)


@SERVER.feature(TEXT_DOCUMENT_DID_CLOSE)
def did_close(
    server: HelixLanguageServer, params: DidCloseTextDocumentParams
) -> None:
    publish_diagnostics(server, params.text_document.uri)
    
    
    
if __name__ == "__main__": 
    print("Helix Language Server started")
    SERVER.start_io()