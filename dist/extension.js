"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const node_1 = require("vscode-languageclient/node");
const child_process_1 = require("child_process");
const path = __importStar(require("path"));
let client;
/**
 * Activate the extension
 * @param context The extension context
 */
function activate(context) {
    console.log('[DEBUG] Activating Helix Language Server Client...');
    const serverOptions = () => {
        return new Promise((resolve, reject) => {
            console.log('[DEBUG] Starting Helix Language Server...');
            const SERVER_SCRIPT_PATH = path.join(__dirname, '..', 'server', 'server.py');
            const HELIX_BINARY_PATH = '/Volumes/Development/Projects/Helix/helix-lang/build/release/universal-llvm-macosx/bin/helix';
            // Spawn the language server process
            console.log(`[DEBUG] Server path: ${SERVER_SCRIPT_PATH}`);
            console.log(`[DEBUG] Helix binary: ${HELIX_BINARY_PATH}`);
            const serverProcess = (0, child_process_1.spawn)('/Volumes/Development/Projects/Helix/helix-lsp/.venv/bin/python', [SERVER_SCRIPT_PATH, HELIX_BINARY_PATH], { stdio: ['pipe', 'pipe', 'pipe'] });
            serverProcess.stdout?.on('data', (data) => console.log(`[DEBUG] Server stdout: ${data.toString()}`));
            serverProcess.stderr?.on('data', (data) => console.error(`[DEBUG] Server stderr: ${data.toString()}`));
            serverProcess.on('close', (code) => console.log(`[DEBUG] Server process exited with code ${code}`));
            resolve({
                writer: serverProcess.stdin,
                reader: serverProcess.stdout,
            });
        });
    };
    const clientOptions = {
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
