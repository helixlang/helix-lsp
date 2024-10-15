import subprocess
import os

from server.helix_server import HelixLanguageServer
class DocumentManager:
    def __init__(self):
        self.documents = {}
    def update_docment(self, uri, text):
        
        ast = self.parsed_text(uri)
        self.documents[uri] = {
            "text": text,
            "ast": ast
        }
    def parsed_text(self, uri):
        process = subprocess.Popen(['helix', uri, "--emit-ast", "--lsp-mode"], stdout=subprocess.PIPE)
        ast = communicate()[0].decode("utf-8")
            
    
    def get_document(self, uri):
        return self.documents.get(uri)
        
class documentHandler:
    from pygls.features import(
        TEXT_DOCUMENT_DID_OPEN,
        TEXT_DOCUMENT_DID_CHANGE,
        TEXT_DOCUMENT_DID_CLOSE
    )
    from pygls.types import (
        DidOpenTextDocumentParams, 
        DidChangeTextDocumentParams, 
        DidCloseTextDocumentParams
        )
    
    @HelixLanguageServer.feature(TEXT_DOCUMENT_DID_OPEN)
    def did_open(server: HelixLanguageServer, params: DidOpenTextDocumentParams):
        uri = params.textDocument.uri
        server.doc_manager.update_document(uri)
    
    @HelixLanguageServer.feature(TEXT_DOCUMENT_DID_CHANGE)
    def did_change(server: HelixLanguageServer, params: DidChangeTextDocumentParams):
        uri = params.textDocument.uri
        changes = params.contentChanges
        text = changes[0].text
        server.doc_manager.update_document(uri, text)
        
    @HeliLanguageServer.feature(TEXT_DOCUMENT_DID_CLOSE)
    def did_close(server: HelixLanguageServer, params: DidCloseTextDocumentParams):
        uri = params.textDocument.uri
        server.doc_manager.close_document(uri, None)
    
        