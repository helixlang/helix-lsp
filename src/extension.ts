import * as vscode from 'vscode';
import { LanguageClient, LanguageClientOptions, StreamInfo } from 'vscode-languageclient/node';
import { spawn, ChildProcess } from 'child_process';
import * as path from 'path';

let client: LanguageClient | undefined;

/**
 * Activate the extension
 * @param context The extension context
 */
export function activate(context: vscode.ExtensionContext): void {
    console.log('[DEBUG] Activating Helix Language Server Client...');

    const serverOptions = (): Promise<StreamInfo> => {
        return new Promise((resolve, reject) => {
            console.log('[DEBUG] Starting Helix Language Server...');

            const SERVER_SCRIPT_PATH = path.join(__dirname, '..', 'server', 'server.py');
            const HELIX_BINARY_PATH = '/Volumes/Development/Projects/Helix/helix-lang/build/release/universal-llvm-macosx/bin/helix';

            // Spawn the language server process
            console.log(`[DEBUG] Server path: ${SERVER_SCRIPT_PATH}`);
            console.log(`[DEBUG] Helix binary: ${HELIX_BINARY_PATH}`);
            const serverProcess: ChildProcess = spawn(
                '/Volumes/Development/Projects/Helix/helix-lsp/.venv/bin/python',
                [SERVER_SCRIPT_PATH, HELIX_BINARY_PATH],
                { stdio: ['pipe', 'pipe', 'pipe'] }
            );

            serverProcess.stdout?.on('data', (data: Buffer) =>
                console.log(`[DEBUG] Server stdout: ${data.toString()}`)
            );
            serverProcess.stderr?.on('data', (data: Buffer) =>
                console.error(`[DEBUG] Server stderr: ${data.toString()}`)
            );
            serverProcess.on('close', (code: number) =>
                console.log(`[DEBUG] Server process exited with code ${code}`)
            );

            resolve({
                writer: serverProcess.stdin!,
                reader: serverProcess.stdout!,
            });
        });
    };

    const clientOptions: LanguageClientOptions = {
        documentSelector: [{ scheme: 'file', language: 'Helix' }],
        synchronize: {
            fileEvents: vscode.workspace.createFileSystemWatcher('**/*.hlx'),
        },
        outputChannel: vscode.window.createOutputChannel('Helix Language Server'),
    };

    client = new LanguageClient(
        'helixLanguageServer',
        'Helix Language Server',
        serverOptions,
        clientOptions
    );

    console.log('[DEBUG] Starting the language client...');
    client.start();

    context.subscriptions.push(client);
}

/**
 * Deactivate the extension
 */
export function deactivate(): Thenable<void> | undefined {
    if (!client) {
        return undefined;
    }
    console.log('[DEBUG] Deactivating Helix Language Server Client...');
    return client.stop();
}
