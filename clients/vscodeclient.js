const vscode = require('vscode');
const { spawn } = require('child_process');
const { createConnection, StreamMessageReader, StreamMessageWriter } = require('vscode-languageserver-protocol');
const path = require('path');

let serverProcess;
let connection;

/**
 * Activate the extension
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
    console.log('Helix Language Server Client is now active.');

    // Start the language server
    startLanguageServer();

    // Watch for opening of specific language files
    context.subscriptions.push(
        vscode.workspace.onDidOpenTextDocument((document) => {
            if (isHelixFile(document)) {
                sendDidOpen(document);
            }
        })
    );

    // Watch for file changes
    context.subscriptions.push(
        vscode.workspace.onDidChangeTextDocument((event) => {
            if (isHelixFile(event.document)) {
                sendDidChange(event.document);
            }
        })
    );

    // Handle closing of files
    context.subscriptions.push(
        vscode.workspace.onDidCloseTextDocument((document) => {
            if (isHelixFile(document)) {
                sendDidClose(document);
            }
        })
    );
}

/**
 * Deactivate the extension
 */
function deactivate() {
    if (serverProcess) {
        serverProcess.kill();
    }
    if (connection) {
        connection.dispose();
    }
    console.log('Helix Language Server Client is now deactivated.');
}

/**
 * Start the Helix Language Server
 */
function startLanguageServer() {
    try {
        // Launch the Python server
        const SERVER_SCRIPT_PATH = path.join(__dirname, 'helix_language_server.py');
        serverProcess = spawn('python', [SERVER_SCRIPT_PATH], { stdio: 'pipe' });

        serverProcess.stdout.on('data', (data) => console.log(`Server: ${data.toString()}`));
        serverProcess.stderr.on('data', (data) => console.error(`Server Error: ${data.toString()}`));

        serverProcess.on('close', (code) => {
            console.log(`Language Server exited with code ${code}`);
        });

        // Establish a stdio connection
        connection = createConnection(
            new StreamMessageReader(serverProcess.stdout),
            new StreamMessageWriter(serverProcess.stdin)
        );

        connection.listen();
        console.log('Helix Language Server connected via stdio.');
    } catch (error) {
        console.error('Failed to start the language server:', error);
    }
}

/**
 * Send `didOpen` notification
 * @param {vscode.TextDocument} document
 */
function sendDidOpen(document) {
    const params = {
        textDocument: {
            uri: document.uri.toString(),
            languageId: document.languageId,
            version: document.version,
            text: document.getText()
        }
    };
    connection.sendNotification('textDocument/didOpen', params);
}

/**
 * Send `didChange` notification
 * @param {vscode.TextDocument} document
 */
function sendDidChange(document) {
    const params = {
        textDocument: {
            uri: document.uri.toString(),
            version: document.version
        },
        contentChanges: [
            {
                text: document.getText()
            }
        ]
    };
    connection.sendNotification('textDocument/didChange', params);
}

/**
 * Send `didClose` notification
 * @param {vscode.TextDocument} document
 */
function sendDidClose(document) {
    const params = {
        textDocument: {
            uri: document.uri.toString()
        }
    };
    connection.sendNotification('textDocument/didClose', params);
}

/**
 * Check if the file is handled by Helix
 * @param {vscode.TextDocument} document
 * @returns {boolean}
 */
function isHelixFile(document) {
    const supportedLanguages = ['yourLanguageId']; // Replace with the language ID
    return supportedLanguages.includes(document.languageId);
}

module.exports = {
    activate,
    deactivate
};
