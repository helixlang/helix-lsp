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
import sys
import traceback
import tempfile

from lsprotocol.types import (
    INITIALIZED,
    TEXT_DOCUMENT_DID_CLOSE,
    TEXT_DOCUMENT_CODE_ACTION,
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_DID_SAVE,
    Diagnostic,
    DiagnosticSeverity,
    DidChangeTextDocumentParams,
    DidCloseTextDocumentParams,
    DidOpenTextDocumentParams,
    PublishDiagnosticsParams,
    DidSaveTextDocumentParams,
    Position,
    Range,
    CodeActionParams,
    CodeAction,
    ExecuteCommandParams,
    CodeActionKind,
    Command,
    TextDocumentItem,
)
from pygls.lsp.server import LanguageServer

# ---------------------------------------------------------------------- #
# Logging Configuration
# ---------------------------------------------------------------------- #
LOG_FILE = os.path.join(os.path.dirname(__file__), "lsp.log")
LOG_CLEAR_INTERVAL = 600  # seconds

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("KairoLSP")
logger.propagate = True

def log_unhandled_exception(exc_type, exc_value, exc_traceback):
    """Global hook for all uncaught exceptions."""
    if issubclass(exc_type, KeyboardInterrupt):
        # Allow graceful shutdown without treating as error
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    tb_str = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    logger.critical("Uncaught exception:\n%s", tb_str)

    # Also write directly to an emergency file in case logging fails
    err_path = os.path.join(os.path.dirname(__file__), "error.log")
    with open(err_path, "a", encoding="utf-8") as f:
        f.write(f"\n[UNCAUGHT] {time.strftime('%Y-%m-%d %H:%M:%S')}\n{tb_str}\n")

# Install global exception handler
sys.excepthook = log_unhandled_exception

def safe_handler(fn):
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            logger.exception(f"Exception in handler {fn.__name__}")
    return wrapper

def clear_log_file() -> None:
    """Clears the log file content."""
    with open(LOG_FILE, "w"):
        pass

clear_log_file()  # empty log on start

@contextmanager
def timer():
    start = time.time()
    yield lambda: time.time() - start


# ---------------------------------------------------------------------- #
# Helper Path Comparison
# ---------------------------------------------------------------------- #
def compare_paths(path1, path2, case_sensitive=True):
    try:
        p1 = Path(path1).resolve()
        p2 = Path(path2).resolve()
    except (FileNotFoundError, OSError):
        p1 = Path(path1).absolute()
        p2 = Path(path2).absolute()

    if not case_sensitive:
        return str(p1).lower() == str(p2).lower()
    return p1 == p2


# ---------------------------------------------------------------------- #
# Optimized CompileCommands
# ---------------------------------------------------------------------- #
class CompileCommands:
    """Optimized class to handle compile_commands.json with caching and fast lookups."""

    def __init__(self, lsp) -> None:
        workspace = lsp.workspace.folders
        self.commands: list[str] = []
        self._cache: dict[str, list[str]] = {}
        self._lock = threading.Lock()

        if not workspace:
            logger.error("No workspace folder found.")
            self.path = None
            return

        uri = next(iter(workspace.values())).uri
        parsed = urlparse(uri)
        win_path = url2pathname(unquote(parsed.path))
        p = pathlib.Path(win_path).absolute()
        if p.drive:
            p = pathlib.Path(p.drive.upper() + str(p)[len(p.drive):])

        self.directory = str(p)
        self.path = str(p / "compile_commands.json")
        self._last_mtime: float = 0.0
        self._commands_map: dict[str, list[str]] = {}

    # ------------------------------------------------------------------ #
    def _reload_if_needed(self) -> None:
        """Reloads compile_commands.json only if modified."""
        if not self.path:
            return
        try:
            mtime = os.path.getmtime(self.path)
        except FileNotFoundError:
            return

        if mtime <= self._last_mtime:
            return

        with self._lock:
            try:
                with open(self.path, "r") as f:
                    data = json.load(f)
            except Exception as e:
                logger.error("Failed to load compile_commands.json: %s", e)
                return

            new_map: dict[str, list[str]] = {}

            for cmd in data:
                file_path = cmd.get("file")
                if not file_path:
                    continue
                abs_path = os.path.abspath(file_path)
                args = cmd.get("arguments")
                if not args:
                    continue

                match args:
                    case str() as arg_str:
                        new_map[os.path.normpath(abs_path).lower()] = arg_str.split()
                    case list() as arg_list if all(isinstance(a, str) for a in arg_list):
                        new_map[os.path.normpath(abs_path).lower()] = arg_list
                    case _:
                        logger.warning("Invalid compile command entry for: %s", file_path)

            self._commands_map = new_map
            self._last_mtime = mtime
            logger.debug("Reloaded compile_commands.json with %d entries", len(new_map))

    # ------------------------------------------------------------------ #
    def load(self, for_file: str) -> None:
        """Loads compile commands for a specific file, using cache when possible."""
        self.commands.clear()
        if not self.path:
            return

        self._reload_if_needed()
        key = os.path.normpath(os.path.abspath(for_file)).lower()

        # Cache hit
        if cached := self._cache.get(key):
            self.commands.extend(cached)
            logger.debug("Cache hit for %s", for_file)
            return

        if args := self._commands_map.get(key):
            self._cache[key] = args
            self.commands.extend(args)
            logger.debug("Loaded compile command for %s: %s", for_file, args)
        else:
            logger.debug("No compile command found for %s", for_file)


def extract_cpp_from_ir(kairo_path: str, compile_db: 'CompileCommands', file: str, line_range: str | None = None) -> str:
    """
    Run the Kairo compiler to emit IR for the given file, trim boilerplate,
    extract the mapped C++ for the specified line range, and return formatted output.
    Respects compile_commands.json from the running LSP server.
    """
    logger = logging.getLogger("KairoLSP")

    if not os.path.exists(kairo_path):
        raise FileNotFoundError(f"Kairo binary not found: {kairo_path}")

    compile_db.load(file)
    cmd = [kairo_path, file, "--emit-ir", "--verbose"]

    if compile_db.commands:
        cmd.extend(compile_db.commands)

    logger.info(f"Running Kairo IR emission for {file}")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    output = proc.stdout

    if not output.strip():
        raise RuntimeError("No output received from Kairo compiler")

    # --- Trim preamble ---
    hdr_pat = re.compile(r"#define __KAIRO_CORE_CXX__.*?#endif", re.DOTALL)
    m = hdr_pat.search(output)
    if m:
        output = output[m.end():]

    # Trim everything after the last #endif (Kairo emits multiple files)
    last_endif = output.rfind("#endif")
    if last_endif != -1:
        output = output[:last_endif + len("#endif")]

    # --- Remove ANSI color codes ---
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    output = ansi_escape.sub('', output)

    # --- Build mapping: file → [lines] ---
    file_lines: dict[str, list[str]] = {}
    current_file = None
    current_macro = None
    current_line = None
    in_guard_section = False

    for raw in output.splitlines():
        line = raw.strip()
        if not line:
            continue

        # detect new file section
        if line.startswith("#define") and len(line.split()) == 3:
            _, macro, path_token = line.split(maxsplit=2)
            current_file = path_token.strip('"')
            current_macro = macro
            current_line = None
            in_guard_section = False
            file_lines.setdefault(current_file, [])
            continue

        if line.startswith("#line") and current_file:
            parts = line.split()
            try:
                ln = int(parts[1])
            except Exception:
                continue

            # second #line 1 marks the start of real code
            if len(parts) == 3 and parts[2] == current_macro:
                if in_guard_section:
                    file_lines[current_file] = []
                in_guard_section = True
                current_line = ln - 1
            elif len(parts) == 2:
                current_line = ln - 1
            continue

        if line.startswith("#"):
            continue

        if current_file is None or current_line is None:
            continue

        lines = file_lines[current_file]
        while len(lines) <= current_line:
            lines.append("")
        if lines[current_line]:
            lines[current_line] += "\n" + raw
        else:
            lines[current_line] = raw
        current_line += 1

    # --- Match file ---
    found_file = next((p for p in file_lines if p.endswith(file)), None)
    if not found_file:
        raise RuntimeError(f"No matching file section found for {file}")

    lines = file_lines[found_file]

    # --- Parse range ---
    if not line_range:
        start_line, end_line = 1, len(lines)
    elif ":" in line_range:
        start_line, end_line = map(int, line_range.split(":"))
    elif "-" in line_range:
        start_line, end_line = map(int, line_range.split("-"))
    else:
        start_line = end_line = int(line_range)

    start_line = max(1, start_line)
    end_line = max(start_line, end_line)

    if start_line > len(lines):
        raise IndexError(f"Start line {start_line} beyond file end ({len(lines)}).")

    isolated = lines[start_line - 1:end_line]
    isolated_code = "\n".join(l for l in isolated if l.strip())
    if not isolated_code.strip():
        raise RuntimeError(f"No content found in range {start_line}-{end_line}.")

    # --- clang-format ---
    with tempfile.NamedTemporaryFile(delete=False, suffix=".cpp", mode="w") as tmp:
        tmp.write(isolated_code)
        tmp_path = tmp.name

    try:
        fmt = subprocess.run(["clang-format", "-style=file", tmp_path],
                             capture_output=True, text=True)
        return fmt.stdout if fmt.returncode == 0 else isolated_code
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

# ---------------------------------------------------------------------- #
# KairoLanguageServer
# ---------------------------------------------------------------------- #
class KairoLanguageServer(LanguageServer):
    """Custom Language Server for Kairo."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.diagnostics: Dict[str, List[Diagnostic]] = {}
        self.last_request_t = time.time()
        self.parse_interval = None
        self.analyze_failed = False
        self.basic_parse_failed = False
        self.kairo_path = sys.argv[1] if len(sys.argv) > 1 else None
        self.compile_db = None

    @property
    def server_capabilities(self):
        caps = super().server_capabilities
        caps.text_document_sync = {
            "openClose": True,
            "change": None,
            "willSave": False,
            "willSaveWaitUntil": False,
            "save": True,
        }
        return caps

    # ------------------------------------------------------------------ #
    def _parse_with_analyze(self, document: TextDocumentItem) -> None:
        with timer() as elapsed:
            self.parse(document, analyze=True)
        self.parse_interval = elapsed()

    def queue_parse(self, document: TextDocumentItem) -> None:
        self.analyze_failed = not self.parse(document, analyze=True)
        self.last_request_t = time.time()
        return

    # ------------------------------------------------------------------ #
    def parse(self, document: TextDocumentItem, analyze: bool = False) -> bool:
        if self.compile_db is None:
            try:
                self.compile_db = CompileCommands(self)
            except Exception as e:
                logger.warning("Lazy re-init of CompileCommands failed: %s", e)

        diagnostics = []
        try:
            uri_path = urlparse(document.uri).path
            decoded_path = unquote(uri_path)
            file_path = os.path.abspath(decoded_path)

            if not self.kairo_path or not os.path.exists(self.kairo_path):
                logger.critical("Kairo binary not found: %s", self.kairo_path)
                raise FileNotFoundError(f"Kairo binary does not exist: {self.kairo_path}")

            command = [self.kairo_path, file_path, "--lsp-mode"]

            if analyze:
                command.append("--emit-ir")

            # Use persistent cached compile_commands
            self.compile_db.load(file_path)
            if self.compile_db.commands:
                command.extend(self.compile_db.commands)


            env = os.environ.copy()

            logger.info("Launching with env:")
            for k, v in env.items():
                logger.info("%s=%s", k, v)

            env["PWD"] = self.compile_db.directory

            logger.info(f"Running command: {' '.join(command)} in {self.compile_db.directory}")
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.compile_db.directory,
                env=env,
            )
            try:
                stdout, stderr = process.communicate(timeout=10)  # 10 second timeout
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                logger.error("Kairo compiler timed out after 10 seconds: %s", command)

            if stderr:
                logger.error("Kairo stderr: %s", stderr.decode("utf-8"))

            if process.returncode == 0:
                self.diagnostics[document.uri] = (document.version, [])
                return True

            result = stdout.decode("utf-8").strip()
            result = self._remove_ansi_colors(result)

            if not result and process.returncode != 0:
                self.diagnostics[document.uri] = (document.version, diagnostics)
                return False

            try:
                json_result = json.loads(result)
                diagnostics = self._convert_to_diagnostics(json_result, file_path)
                self.diagnostics[document.uri] = (document.version, diagnostics)
            
            except json.JSONDecodeError as e:
                logger.error("Failed to parse JSON from Kairo output: %s\nOutput: %s", e, result)
                self.diagnostics[document.uri] = (document.version, diagnostics)
                return False

        except Exception as e:
            traceback.print_exc()
            logger.error("Error parsing document %s: %s", document.uri, e)

        if not analyze:
            return not any(d.severity == DiagnosticSeverity.Error for d in diagnostics)
        return not bool(diagnostics)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _remove_ansi_colors(text: str) -> str:
        ansi_escape_pattern = re.compile(r"(?:\x1b|\033|\u001b|\001b)(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        return ansi_escape_pattern.sub("", text)

    @staticmethod
    def _convert_to_diagnostics(json_result: dict, file_path: str) -> List[Diagnostic]:
        diagnostics = []
        for error in json_result.get("error", {}).get("errors", []):
            severity = {
                "error": DiagnosticSeverity.Error,
                "note": DiagnosticSeverity.Information,
                "warn": DiagnosticSeverity.Warning,
                "fatal": DiagnosticSeverity.Error,
            }.get(str(error["level"]).strip(), DiagnosticSeverity.Information)

            if not compare_paths(error["file"].replace("\\\\", "\\"), file_path):
                continue

            diagnostics.append(
                Diagnostic(
                    message=error["msg"],
                    severity=severity,
                    range=Range(
                        start=Position(line=int(error["line"]) - 1, character=int(error["col"])),
                        end=Position(
                            line=int(error["line"]) - 1,
                            character=int(error["col"]) + int(error["offset"]),
                        ),
                    ),
                )
            )
        return diagnostics


# ---------------------------------------------------------------------- #
# LSP Feature Registration
# ---------------------------------------------------------------------- #
SERVER = KairoLanguageServer("KairoLSP", "1.0")


@SERVER.feature(INITIALIZED)
def on_initialized(server: KairoLanguageServer, params: Any) -> None:
    logger.info("Kairo Language Server initialized.")
    try:
        server.compile_db = CompileCommands(server)
        logger.info("CompileCommands initialized successfully.")
    except Exception as e:
        logger.error("Failed to initialize CompileCommands: %s", e)


@SERVER.feature(TEXT_DOCUMENT_DID_OPEN)
def did_open(server: KairoLanguageServer, params: DidOpenTextDocumentParams) -> None:
    doc = server.workspace.get_text_document(params.text_document.uri)
    server.queue_parse(doc)
    send_diagnostics(server, params.text_document.uri)


@SERVER.feature(TEXT_DOCUMENT_DID_CLOSE)
def did_close(server: KairoLanguageServer, params: DidCloseTextDocumentParams) -> None:
    server.diagnostics.pop(params.text_document.uri, None)
    send_diagnostics(server, params.text_document.uri)


@SERVER.feature(TEXT_DOCUMENT_DID_SAVE)
def did_save(server: KairoLanguageServer, params: DidChangeTextDocumentParams) -> None:
    """Handles document saving."""
    uri = getattr(params.text_document, "uri", None)
    if not uri:
        logger.warning("DidSave event missing URI: %s", params)
        return
    doc = server.workspace.get_text_document(uri)
    server.queue_parse(doc)
    send_diagnostics(server, uri)

@SERVER.command("kairo.showIR")
def show_ir(server: KairoLanguageServer, params: ExecuteCommandParams):
    """Handles actual IR generation when command is invoked."""
    logger.info(f"Received kairo.showIR for {params}")
    try:
        uri, start_line, end_line = params.arguments
        file = Path(url2pathname(unquote(urlparse(uri).path))).absolute()
        line_range = f"{start_line}:{end_line}"

        result = extract_cpp_from_ir(
            server.kairo_path, server.compile_db, str(file), line_range
        )
        return result
    except Exception as e:
        logger.exception("Show IR failed")
        return f"Error: {e}"

def send_diagnostics(server: KairoLanguageServer, uri: str) -> None:
    diag = server.diagnostics.get(uri)
    if not diag:
        return
    version, diagnostics = diag
    server.text_document_publish_diagnostics(
        PublishDiagnosticsParams(uri=uri, version=version, diagnostics=diagnostics)
    )
    server.diagnostics.clear()


# ---------------------------------------------------------------------- #
# Log maintenance
# ---------------------------------------------------------------------- #
class LogClearerThread(threading.Thread):
    def __init__(self, interval: int) -> None:
        super().__init__(daemon=True)
        self.interval = interval

    def run(self) -> None:
        while True:
            time.sleep(self.interval)
            clear_log_file()
            logger.info("Log file cleared.")


# ---------------------------------------------------------------------- #
# Entrypoint
# ---------------------------------------------------------------------- #
if __name__ == "__main__":
    logger.info("Starting Kairo Language Server")
    try:
        LogClearerThread(LOG_CLEAR_INTERVAL).start()
        SERVER.start_io()
    except Exception as e:
        logger.critical("Server encountered a fatal error: %s", e)
        with open(os.path.join(os.path.dirname(__file__), "error.log"), "a") as f:
            f.write(f"Fatal error: {e}\n")
# ---------------------------------------------------------------------- #