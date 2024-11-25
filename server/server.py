import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, List
from urllib.parse import unquote, urlparse

from lsprotocol.types import (
    INITIALIZED,
    TEXT_DOCUMENT_DID_CLOSE,
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_DID_SAVE,
    Diagnostic,
    DiagnosticSeverity,
    DidChangeTextDocumentParams,
    DidCloseTextDocumentParams,
    DidOpenTextDocumentParams,
    Position,
    PublishDiagnosticsParams,
    Range,
    TextDocumentItem,
)
from pygls.lsp.server import LanguageServer

# Constants
LOG_FILE = os.path.join(os.path.dirname(sys.argv[1]), "lsp.log")
LOG_CLEAR_INTERVAL = 600  # Time in seconds to clear logs periodically

# Logger Configuration
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("HelixLSP")
logger.propagate = False

# Helper Functions


def clear_log_file() -> None:
    """Clears the log file content."""
    with open(LOG_FILE, "w"):
        pass


clear_log_file()  # Ensure log file is empty at start


@contextmanager
def timer():
    start = time.time()
    try:
        yield lambda: time.time() - start
    finally:
        time.time()


class HelixLanguageServer(LanguageServer):
    """Custom Language Server for Helix."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.diagnostics: Dict[str, List[Diagnostic]] = {}
        self.last_request_t = time.time()
        self.parse_interval = None
        self.analyze_failed = False
        self.basic_parse_failed = False

    def _parse_with_analyze(self, document: TextDocumentItem) -> None:
        """Parses a document with --emit-ir flag."""
        with timer() as elapsed:
            self.parse(document, analyze=True)

        self.parse_interval = elapsed()

    def queue_parse(self, document: TextDocumentItem) -> None:
        """Queues a document for parsing. sometimes parses a with --emit-ir flag"""
        if (
            self.analyze_failed
            or self.parse_interval is None
            or time.time() - self.last_request_t > self.parse_interval
        ):
            self.analyze_failed = not self.parse(document, analyze=True)
            self.last_request_t = time.time()
            return

        not self.parse(document)

    def parse(self, document: TextDocumentItem, analyze: bool = False) -> bool:
        """
        Parses a document using the Helix binary in LSP mode and returns diagnostics.

        Args:
            document (TextDocumentItem): Document to parse.

        Returns:
            bool: True if parsing was successful, False otherwise.
        """
        diagnostics = []

        try:
            uri_path = urlparse(document.uri).path
            decoded_path = unquote(uri_path)
            file_path = os.path.abspath(decoded_path.lstrip('/'))

            helix_path = sys.argv[1]
            if not os.path.exists(helix_path):
                logger.critical('Helix binary not found at: {}', helix_path)
                raise FileNotFoundError(
                    f"Helix binary does not exist: {helix_path}")

            command = [helix_path, file_path, "--lsp-mode"]

            if analyze:
                command.append("--emit-ir")

            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()

            if stderr:
                logger.error('Helix stderr: {}', stderr.decode('utf-8'))

            result = stdout.decode('utf-8').strip()
            result = self._remove_ansi_colors(result)

            if not result or process.returncode != 0:
                logger.warning(
                    'Empty or invalid result from Helix for {}', file_path)
                self.diagnostics[document.uri] = []

            json_result = json.loads(result)
            diagnostics = self._convert_to_diagnostics(json_result)

            self.diagnostics[document.uri] = (document.version, diagnostics)
            logger.debug('Parsed diagnostics for {}: {}',
                         file_path, diagnostics)
        except Exception as e:
            logger.error('Error parsing document {}: {}', document.uri, e)

        if not analyze:
            return not bool([d for d in diagnostics if d.severity == DiagnosticSeverity.Error])

        return not bool(diagnostics)

    @staticmethod
    def _remove_ansi_colors(text: str) -> str:
        """Removes ANSI escape sequences from text."""
        ansi_escape_pattern = re.compile(
            r"(?:\x1b|\033|\u001b|\001b)" r"(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])"
        )

        return ansi_escape_pattern.sub('', text)

    @staticmethod
    def _convert_to_diagnostics(json_result: dict) -> List[Diagnostic]:
        """Converts JSON output to a list of LSP diagnostics."""
        diagnostics = []
        for error in json_result.get("error", {}).get("errors", []):
            severity = {
                "error": DiagnosticSeverity.Error,
                "note": DiagnosticSeverity.Hint,
                "warn": DiagnosticSeverity.Warning,
                "fatal": DiagnosticSeverity.Error,
            }.get(str(error["level"]).strip(), DiagnosticSeverity.Information)

            diagnostics.append(
                Diagnostic(
                    message=error["msg"],
                    severity=severity,
                    range=Range(
                        start=Position(
                            line=int(error["line"]) - 1,
                            character=int(error["col"]),
                        ),
                        end=Position(
                            line=int(error["line"]) - 1,
                            character=int(error["col"]) + int(error["offset"]),
                        ),),))
        return diagnostics


SERVER = HelixLanguageServer("HelixLSP", "1.0")


@SERVER.feature(INITIALIZED)
def on_initialized(server: HelixLanguageServer, params: Any) -> None:
    """Handles server initialization."""
    logger.info("Helix Language Server initialized.")


@SERVER.feature(TEXT_DOCUMENT_DID_OPEN)
def did_open(server: HelixLanguageServer, params: DidOpenTextDocumentParams) -> None:
    """Handles document opening."""
    logger.info('Document opened: {}', params.text_document.uri)
    doc = server.workspace.get_text_document(params.text_document.uri)
    server.queue_parse(doc)
    send_diagnostics(server, params.text_document.uri)


@SERVER.feature(TEXT_DOCUMENT_DID_CLOSE)
def did_close(server: HelixLanguageServer, params: DidCloseTextDocumentParams) -> None:
    """Handles document closing."""
    logger.info('Document closed: {}', params.text_document.uri)
    server.diagnostics.pop(params.text_document.uri, None)
    send_diagnostics(server, params.text_document.uri)


@SERVER.feature(TEXT_DOCUMENT_DID_SAVE)
def did_save(server: HelixLanguageServer, params: DidChangeTextDocumentParams) -> None:
    """Handles document saving."""
    logger.info('Document saved: {}', params.text_document.uri)
    doc = server.workspace.get_text_document(params.text_document.uri)
    server.queue_parse(doc)
    send_diagnostics(server, params.text_document.uri)


def send_diagnostics(server: HelixLanguageServer, uri: str) -> None:
    """Sends diagnostics to the client."""
    logger.debug('Diagnostics sent for {}: {}',
                 uri, server.diagnostics.get(uri))
    for _uri, (version, diagnostics) in server.diagnostics.items():
        diagnostic = PublishDiagnosticsParams(
            uri=_uri,
            version=version,
            diagnostics=diagnostics,
        )
        server.text_document_publish_diagnostics(diagnostic)

    server.diagnostics.clear()


class LogClearerThread(threading.Thread):
    """Thread for clearing logs periodically."""

    def __init__(self, interval: int) -> None:
        super().__init__(daemon=True)
        self.interval = interval

    def run(self) -> None:
        while True:
            time.sleep(self.interval)
            clear_log_file()
            logger.info("Log file cleared.")


if __name__ == "__main__":
    logger.info("Starting Helix Language Server")
    try:
        LogClearerThread(LOG_CLEAR_INTERVAL).start()
        SERVER.start_io()
    except Exception as e:
        logger.critical('Server encountered a fatal error: {}', e)
