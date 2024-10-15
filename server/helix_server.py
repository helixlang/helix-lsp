from pygls.server import LanguageServer

from server import DocumentManager


class HelixLanguageServer(LanguageServer):
    def __init__(self):
        super().__init__('helix-lsp', 'v0.1')
        self.doc_manager = DocumentManager()


if __name__ == '__main__':
    server = HelixLanguageServer()
    server.start_io()
