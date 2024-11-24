const vscode = require('vscode');
const { LanguageClient, StreamInfo } = require('vscode-languageclient/node');
const net = require('net');
const fs = require('fs');
const path = require('path');

let client;

console.log('dir:', __dirname);

function activate(context) {
    const configPath = path.join(__dirname, '..', '..', 'helix-lsp', 'config.json');

    const interval = setInterval(() => {
        if (fs.existsSync(configPath)) {
            clearInterval(interval);

            try {
                const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
                const port = config.port;

                if (port) {
                    startLanguageClient(port, context);
                } else {
                    throw new Error('Port not found in config.json');
                }
            } catch (error) {
                console.error(`Failed to read config.json: ${error.message}`);
            }
        }
    }, 1000);
}

function startLanguageClient(port, context) {
    const serverOptions = () => {
        return new Promise((resolve, reject) => {
            const socket = net.connect(port, '127.0.0.1', () => {
                console.log(`Connected to language server on port ${port}`);
                const streamInfo = {
                    writer: socket,
                    reader: socket
                };
                resolve(streamInfo);
            });

            socket.on('error', (err) => {
                console.error('Socket error:', err);
                reject(err);
            });
        });
    };

    const clientOptions = {
        documentSelector: [{ scheme: 'file', language: 'helix' }],
        traceOutputChannel: vscode.window.createOutputChannel('Helix Language Server'),
        outputChannel: vscode.window.createOutputChannel('Helix LSP Diagnostics'),
        synchronize: {
            fileEvents: vscode.workspace.createFileSystemWatcher('**/.hlx')
        },
        middleware: {
            didChange: (change, next) => {
                // Send the first didChange request
                next(change);

                // Send the second didChange request with a short delay
                setTimeout(() => {
                    console.log('Sending second didChange request...');
                    next(change);
                }, 500);  // Adjust delay if necessary
            }
        }
    };

    client = new LanguageClient('helixLanguageServer', 'Helix Language Server', serverOptions, clientOptions);
    client.start();

    context.subscriptions.push(client);
}

function deactivate() {
    return client ? client.stop() : undefined;
}

module.exports = {
    activate,
    deactivate
};
