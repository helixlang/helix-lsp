from concurrent.futures import Future
import json
import logging
import os
import pathlib
import re
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
import traceback
from typing import Any, Dict, List
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname
from pathlib import Path

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
    DidChangeWatchedFilesParams,
    Position,
    PublishDiagnosticsParams,
    Range,
    TextDocumentItem,
    WorkspaceFolder,
)
from pygls.lsp.server import LanguageServer

# Constants
LOG_FILE = os.path.join(os.path.dirname(__file__), "lsp.log")
LOG_CLEAR_INTERVAL = 600  # Time in seconds to clear logs periodically

# Logger Configuration
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("HelixLSP")
logger.propagate = True

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

def compare_paths(path1, path2, case_sensitive=True):
    # Convert to Path objects
    p1 = Path(path1)
    p2 = Path(path2)
    
    # Resolve to absolute, normalized paths
    try:
        resolved_p1 = p1.resolve()
        resolved_p2 = p2.resolve()
    except (FileNotFoundError, OSError):
        # If paths don't exist, fall back to normalization without resolving
        resolved_p1 = p1.absolute().normalize()
        resolved_p2 = p2.absolute().normalize()
    
    # Compare paths, accounting for case sensitivity
    if case_sensitive:
        return resolved_p1 == resolved_p2
    
    return resolved_p1.lower() == resolved_p2.lower()

class CompileCommands:
    """Class to handle compile commands."""

    def __init__(self, lsp) -> None:
        workspace = lsp.workspace.folders

        if not workspace:
            logger.error('No workspace folder found.')
            self.path = None
            self.commands = []
            return

        uri = (list(workspace.values())[0]).uri
        parsed = urlparse(uri)
        win_path = url2pathname(unquote(parsed.path))
        # normalize drive to uppercase
        p = pathlib.Path(win_path).absolute()
        if p.drive:
            p = pathlib.Path(p.drive.upper() + str(p)[len(p.drive):])
        self.path = str(p / "compile_commands.json")

        self.commands = []

    def load(self, for_file: str) -> None:
        """Loads compile commands from a JSON file."""
        if not self.path:
            return

        if not os.path.exists(self.path):
            logger.error('Compile commands file not found: %s', self.path)
            return

        with open(self.path, 'r') as f:
            cmds = json.load(f)

        norm_for_file = os.path.normcase(os.path.abspath(for_file))

        for cmd in cmds:
            file_path = os.path.normcase(os.path.abspath(cmd.get('file', '')))
            if file_path == norm_for_file:
                command = cmd.get('arguments')
                if command:
                    if isinstance(command, str):
                        # split string into args
                        self.commands.extend(command.split())
                    elif isinstance(command, list):
                        # already a list of args
                        self.commands.extend(command)
                break
        else:
            logger.warning('No compile command found for file: %s', for_file)
            return

        logger.info('Loaded compile commands for %s: %s', for_file, self.commands)

class HelixLanguageServer(LanguageServer):
    """Custom Language Server for Helix."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.diagnostics: Dict[str, List[Diagnostic]] = {}
        self.last_request_t = time.time()
        self.parse_interval = None
        self.analyze_failed = False
        self.basic_parse_failed = False

    @property
    def server_capabilities(self):
        """Override server capabilities."""
        capabilities = super().server_capabilities
        capabilities.text_document_sync = {
            "openClose": True,
            "change": None,  # Disable incremental sync
            "willSave": False,
            "willSaveWaitUntil": False,
            "save": True,
        }
        
        return capabilities
    
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
                logger.critical('Helix binary not found at: %s', helix_path)
                raise FileNotFoundError(
                    f"Helix binary does not exist: {helix_path}")
            
            # we also need to add compile commands from compile_commands.json if the file matches
            # we keep going up the path until we find compile_commands.json
            compile_commands_path = None
            command = [helix_path, file_path, "--lsp-mode"]
            
            cmds = CompileCommands(self)
            cmds.load(file_path)
            
            if cmds.commands:
                command.extend(cmds.commands)
                logger.debug('Loaded compile commands for %s: %s', file_path, cmds)

            if analyze:
                command.append("--emit-ir")

            # output cmd to stderr
            sys.stderr.write(f"Command: {command}\n")
            sys.stderr.flush()

            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()

            if stderr:
                logger.error('Helix stderr: %s', stderr.decode('utf-8'))

            if process.returncode == 0:
                logger.info('Compile successful for %s', file_path)
                self.diagnostics[document.uri] = (document.version, [])
                return True

            result = stdout.decode('utf-8').strip()
            result = self._remove_ansi_colors(result)
            
            sys.stderr.write(f"Result: {result}\n")
            sys.stderr.flush()
            
            if not result and process.returncode != 0:
                logger.warning('Empty or invalid result from Helix for %s', str(file_path))
                self.diagnostics[document.uri] = (document.version, diagnostics)
                return False

            json_result = json.loads(result)
            diagnostics = self._convert_to_diagnostics(json_result, file_path)

            self.diagnostics[document.uri] = (document.version, diagnostics)
            logger.debug('Parsed diagnostics for %s: %s',
                            file_path, diagnostics)
        except Exception as e:
            # print the entire traceback
            traceback.print_exc()
            logger.error('Error parsing document {}: {}', str(document.uri), str(e))

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
    def _convert_to_diagnostics(json_result: dict, file_path: str) -> List[Diagnostic]:
        """Converts JSON output to a list of LSP diagnostics."""
        diagnostics = []
        for error in json_result.get("error", {}).get("errors", []):
            severity = {
                "error": DiagnosticSeverity.Error,
                "note": DiagnosticSeverity.Information,
                "warn": DiagnosticSeverity.Warning,
                "fatal": DiagnosticSeverity.Error,
            }.get(str(error["level"]).strip(), DiagnosticSeverity.Information)
        
            if not compare_paths(error["file"].replace("\\\\", "\\"), file_path):
                logger.warning('File path mismatch: {} != {}',
                               os.path.abspath(error["file"].lstrip('/')), file_path)
                continue

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
    logger.info('Document opened: %s', params.text_document.uri)
    doc = server.workspace.get_text_document(params.text_document.uri)
    server.queue_parse(doc)
    send_diagnostics(server, params.text_document.uri)


@SERVER.feature(TEXT_DOCUMENT_DID_CLOSE)
def did_close(server: HelixLanguageServer, params: DidCloseTextDocumentParams) -> None:
    """Handles document closing."""
    logger.info('Document closed: %s', params.text_document.uri)
    server.diagnostics.pop(params.text_document.uri, None)
    send_diagnostics(server, params.text_document.uri)


@SERVER.feature(TEXT_DOCUMENT_DID_SAVE)
def did_save(server: HelixLanguageServer, params: DidChangeTextDocumentParams) -> None:
    """Handles document saving."""
    logger.info('Document saved: %s', params.text_document.uri)
    doc = server.workspace.get_text_document(params.text_document.uri)
    server.queue_parse(doc)
    send_diagnostics(server, params.text_document.uri)

# @SERVER.feature("workspace/didChangeWatchedFiles")
# def did_change_watched_files(server: HelixLanguageServer, params: DidChangeWatchedFilesParams) -> None:
#     """Handles document saving."""
#     logger.info('Document saved: %s', params.text_document.uri)
#     doc = server.workspace.get_text_document(params.text_document.uri)
#     server.queue_parse(doc)
#     send_diagnostics(server, params.text_document.uri)

def send_diagnostics(server: HelixLanguageServer, uri: str) -> None:
    """Sends diagnostics to the client."""
    logger.debug('Diagnostics sent for %s: %s',
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
        logger.critical('Server encountered a fatal error: %s', e)
        # save the error to the log file
        with open(os.path.join(os.path.dirname(__file__), "error.log"), "a") as f:
            f.write(f"Fatal error: {e}\n")
