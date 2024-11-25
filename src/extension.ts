import { ChildProcess, spawn } from 'child_process';
import * as path from 'path';
import * as vscode from 'vscode';
import { LanguageClient, LanguageClientOptions, StreamInfo } from 'vscode-languageclient/node';

let client: LanguageClient | undefined;

/**
 * Activate the extension
 * @param context The extension context
 */
export async function activate(context: vscode.ExtensionContext): Promise<void> {
    try {
        const helixPath = await getOrPromptHelixCompilerPath();
        if (!helixPath) {
            vscode.window.showErrorMessage('Helix compiler path not set. Extension will be deactivated.');
            return;
        }

        const serverOptions = createServerOptions(helixPath);
        const clientOptions = createClientOptions();

        client = new LanguageClient(
            'HelixVscodeLSP',
            'Helix Language Support',
            serverOptions,
            clientOptions
        );

        client.start();

        context.subscriptions.push(client);
        context.subscriptions.push(
            vscode.commands.registerCommand('helix.restartLanguageServer', async () => {
                await restartLanguageServer(context, helixPath);
            })
        );

    } catch (error) {
        vscode.window.showErrorMessage(`Failed to activate Helix Language Server Client: ${error}`);
        console.error(`[ERROR] Activation error: ${error}`);
    }
}

/**
 * Restart the Helix Language Server.
 * @param context The extension context.
 * @param helixPath The Helix compiler path.
 */
async function restartLanguageServer(context: vscode.ExtensionContext, helixPath: string): Promise<void> {
    try {
        if (client) {
            vscode.window.showInformationMessage('Stopping Helix Language Server...');
            await client.stop();
        }

        const serverOptions = createServerOptions(helixPath);
        const clientOptions = createClientOptions();

        client = new LanguageClient(
            'HelixVscodeLSP',
            'Helix Language Support',
            serverOptions,
            clientOptions
        );

        vscode.window.showInformationMessage('Restarting Helix Language Server...');
        client.start();

        context.subscriptions.push(client);
    } catch (error) {
        vscode.window.showErrorMessage(`Failed to restart Helix Language Server: ${error}`);
        console.error(`[ERROR] Restart error: ${error}`);
    }
}

/**
 * Deactivate the extension
 */
export function deactivate(): Thenable<void> | undefined {
    if (!client) {
        return undefined;
    }
    vscode.window.showInformationMessage('Deactivating Helix Language Server Client...');
    return client.stop();
}

/**
 * Get the Helix compiler path from VS Code settings or prompt the user if not set.
 * @returns The Helix compiler path or `undefined` if the user cancels the input.
 */
async function getOrPromptHelixCompilerPath(): Promise<string> {
    const config = vscode.workspace.getConfiguration('helix');
    let helixPath: string | undefined = config.get<string>('compilerPath');
    let helixPathValid = false;

    if (helixPath) {
        try {
            await vscode.workspace.fs.stat(vscode.Uri.file(helixPath));
            helixPathValid = true;
        } catch (error) {
            console.error(`[ERROR] Helix compiler path error: ${error}`);
        }
    }

    if (!helixPathValid) {
        vscode.window.showErrorMessage(`Helix compiler path does not exist or is not executable: ${helixPath}`);
        
        helixPath = await vscode.window.showInputBox({
            prompt: 'Enter the full path to the Helix compiler (helix binary)',
            placeHolder: '/path/to/helix',
        });

        if (helixPath) {
            await config.update('compilerPath', helixPath, vscode.ConfigurationTarget.Global);
            vscode.window.showInformationMessage(`Helix compiler path set to: ${helixPath}`);
        }
    }

    return helixPath || '';
}

/**
 * Create server options for the language client.
 * @returns A promise that resolves with the StreamInfo object.
 */
function createServerOptions(helixPath: string): () => Promise<StreamInfo> {
    return (): Promise<StreamInfo> => {
        return new Promise((resolve, reject) => {
            const SERVER_SCRIPT_PATH = path.resolve(__dirname, '..', 'server', 'server.py');

            console.log(`[INFO] Server script path: ${SERVER_SCRIPT_PATH}`);
            console.log(`[INFO] Helix binary path: ${helixPath}`);

            const serverProcess: ChildProcess = spawn(
                '/Volumes/Development/Projects/Helix/helix-lsp/.venv/bin/python',
                [SERVER_SCRIPT_PATH, helixPath],
                { stdio: ['pipe', 'pipe', 'pipe'] }
            );

            serverProcess.stdout?.on('data', (data: Buffer) =>
                console.log(`[INFO] Server stdout: ${data.toString()}`)
            );
            serverProcess.stderr?.on('data', (data: Buffer) =>
                console.error(`[ERROR] Server stderr: ${data.toString()}`)
            );
            serverProcess.on('error', (error) => {
                console.error(`[ERROR] Server process error: ${error.message}`);
                reject(error);
            });
            serverProcess.on('close', (code: number) => {
                if (code !== 0) {
                    console.error(`[ERROR] Server process exited with code ${code}`);
                    reject(new Error(`Server process exited with code ${code}`));
                } else {
                    console.log(`[INFO] Server process exited successfully with code ${code}`);
                }
            });

            resolve({
                writer: serverProcess.stdin!,
                reader: serverProcess.stdout!,
            });
        });
    };
}

/**
 * Create client options for the language client.
 * @returns LanguageClientOptions for the client configuration.
 */
function createClientOptions(): LanguageClientOptions {
    return {
        documentSelector: [{ scheme: 'file', language: 'Helix' }],
        synchronize: {
            fileEvents: vscode.workspace.createFileSystemWatcher('**/*.hlx'),
        },
        outputChannel: vscode.window.createOutputChannel('Helix Language Server'),
    };
}
