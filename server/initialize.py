from pygls.features import INITIALIZE
from pygls.types import InitializeParams, InitializeResult

from server.helix_server import HelixLanguageServer

@HelixLanguageServer.feature(INITIALIZE)
def initialize(server: HelixLanguageServer, params: InitializeParams):
    capabilities = {
        'capabilities': {
            'textDocumentSync' : 2,
            'definitionProvider': True,
            'hoverProvider': True,
            'documentSymbolProvider': True,
            'workspaceSymbolProvider': True,
        }
    }
    return InitializeResult(**capabilities)
    