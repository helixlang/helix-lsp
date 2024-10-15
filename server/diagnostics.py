from pygls.types import Diagnostic, DiagnosticSeverity, Range, Position
import subprocess
from server.helix_server import HelixLanguageServer

def send_diagnostics(server:HelixLanguageServer, uri: str):
    document = server.doc_manager.get_document(uri)
    Diagnostic = []
    if document:
        process = subprocess.Popen(['helix', uri,"--lsp-mode"], stdout=subprocess.PIPE)
        result = process.communicate()[0].decode("utf-8")
        if result:
            
            
            
                