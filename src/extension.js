"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
var vscode = require("vscode");
var node_1 = require("vscode-languageclient/node");
var child_process_1 = require("child_process");
var path = require("path");
var client;
/**
 * Activate the extension
 * @param context The extension context
 */
function activate(context) {
    console.log('[DEBUG] Activating Helix Language Server Client...');
    var serverOptions = function () {
        return new Promise(function (resolve, reject) {
            var _a, _b;
            console.log('[DEBUG] Starting Helix Language Server...');
            var SERVER_SCRIPT_PATH = path.join(__dirname, '..', 'server', 'server.py');
            var HELIX_BINARY_PATH = '/Volumes/Development/Projects/Helix/helix-lang/build/release/universal-llvm-macosx/bin/helix';
            // Spawn the language server process
            console.log("[DEBUG] Server path: ".concat(SERVER_SCRIPT_PATH));
            console.log("[DEBUG] Helix binary: ".concat(HELIX_BINARY_PATH));
            var serverProcess = (0, child_process_1.spawn)('/Volumes/Development/Projects/Helix/helix-lsp/.venv/bin/python', [SERVER_SCRIPT_PATH, HELIX_BINARY_PATH], { stdio: ['pipe', 'pipe', 'pipe'] });
            (_a = serverProcess.stdout) === null || _a === void 0 ? void 0 : _a.on('data', function (data) {
                return console.log("[DEBUG] Server stdout: ".concat(data.toString()));
            });
            (_b = serverProcess.stderr) === null || _b === void 0 ? void 0 : _b.on('data', function (data) {
                return console.error("[DEBUG] Server stderr: ".concat(data.toString()));
            });
            serverProcess.on('close', function (code) {
                return console.log("[DEBUG] Server process exited with code ".concat(code));
            });
            resolve({
                writer: serverProcess.stdin,
                reader: serverProcess.stdout,
            });
        });
    };
    var clientOptions = {
        documentSelector: [{ scheme: 'file', language: 'Helix' }],
        synchronize: {
            fileEvents: vscode.workspace.createFileSystemWatcher('**/*.hlx'),
        },
        outputChannel: vscode.window.createOutputChannel('Helix Language Server'),
    };
    client = new node_1.LanguageClient('helixLanguageServer', 'Helix Language Server', serverOptions, clientOptions);
    console.log('[DEBUG] Starting the language client...');
    client.start();
    context.subscriptions.push(client);
}
/**
 * Deactivate the extension
 */
function deactivate() {
    if (!client) {
        return undefined;
    }
    console.log('[DEBUG] Deactivating Helix Language Server Client...');
    return client.stop();
}
