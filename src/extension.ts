import {ChildProcess, spawn} from 'child_process';
import * as path from 'path';
import * as vscode from 'vscode';
import {LanguageClient, LanguageClientOptions, StreamInfo} from 'vscode-languageclient/node';

let client: LanguageClient|undefined;

/**
 * Activate the extension
 * @param context The extension context
 */
export async function activate(context: vscode.ExtensionContext):
    Promise<void> {
  try {
    context.subscriptions.push(vscode.commands.registerCommand(
        'helix.restartLanguageServer', async () => {
          await restartLanguageServer(context, helixPath);
        }));

    const helixPath =
        await getOrPromptHelixCompilerPath();  // points to helix/bin/helix
    if (!helixPath) {
      vscode.window.showErrorMessage(
          'Helix compiler path not set. Extension will be deactivated.');
      return;
    }

    const venvPath =
        await createVirtualEnv(path.resolve(helixPath, '..', '..'));
    if (!venvPath) {
      vscode.window.showErrorMessage(
          'Virtual environment creation failed. Extension will be deactivated.');
      return;
    }

    const serverOptions = createServerOptions(helixPath, venvPath);
    const clientOptions = createClientOptions();

    client = new LanguageClient(
        'HelixVscodeLSP', 'Helix Language Support', serverOptions,
        clientOptions);

    client.start();

    context.subscriptions.push(client);
  } catch (error) {
    vscode.window.showErrorMessage(
        `Failed to activate Helix Language Server Client: ${error}`);
    console.error(`[ERROR] Activation error: ${error}`);
  }
}

/**
 * find the installed python path
 */
async function findPython(): Promise<string> {
  /// look for both python and python3
  var pythonPaths =
      [{command: 'python', found: false}, {command: 'python3', found: false}];

  for (var i = 0; i < pythonPaths.length; i++) {
    try {
      await vscode.workspace.fs.stat(vscode.Uri.file(pythonPaths[i].command));
      pythonPaths[i].found = true;
    } catch (error) {
      console.error(`[ERROR] Python path error: ${error}`);
    }
  }

  // if pyhton3 is found, return it
  if (pythonPaths[1].found) {
    return pythonPaths[1].command;
  }

  if (pythonPaths[0].found) {
    return pythonPaths[0].command;
  }

  // if no python is found, prompt the user
  var pythonPath;
  vscode.window.showErrorMessage(
      `Python path does not exist or is not executable: python or python3`);

  while (!pythonPath) {
    pythonPath = await vscode.window.showInputBox({
      prompt:
          'Could not find python. Please enter the full path or command to python',
      placeHolder: '/path/to/python',
    });

    if (pythonPath) {
      try {
        await vscode.workspace.fs.stat(vscode.Uri.file(pythonPath));
        return pythonPath;
      } catch (error) {
        console.error(`[ERROR] Python path error: ${error}`);
        pythonPath = '';
      }
    }

    // sleep for 4 seconds
    await new Promise((resolve) => setTimeout(resolve, 4000));
  }

  return pythonPath || '';
}

/**
 * Create a virtual environment for the Helix Language Server. and return the
 * python executable path
 * @param pythonPath The python path.
 * @param helixCompilerDir The Helix compiler root dir, the bin is at
 *     `helixCompilerDir/bin/helix`
 * @param envName The name of the virtual environment.
 */
async function createVirtualEnv(
    helixCompilerDir: string, envName = 'helix-lsp-venv'): Promise<string> {
  const venvDir = path.join(helixCompilerDir, envName);
  const venvPythonPathUnix = path.join(venvDir, 'bin', 'python');
  const venvPythonPathWin = path.join(venvDir, 'Scripts', 'python.exe');

  // check if the virtual environment already exists
  try {
    await vscode.workspace.fs.stat(vscode.Uri.file(venvDir));
    if (process.platform === 'win32') {
      await vscode.workspace.fs.stat(vscode.Uri.file(venvPythonPathWin));
      return venvPythonPathWin;
    } else {
      await vscode.workspace.fs.stat(vscode.Uri.file(venvPythonPathUnix));
      return venvPythonPathUnix;
    }
  } catch (error) {
    console.error(`[INFO] Virtual environment does not exist: ${error}`);
  }


  const pythonPath = await findPython();
  if (!pythonPath) {
    vscode.window.showErrorMessage(
        'Python path not set. Extension will be deactivated.');
    return '';
  }

  // create the virtual environment

  vscode.window.showInformationMessage('Creating virtual environment...');

  try {
    await vscode.workspace.fs.createDirectory(vscode.Uri.file(venvDir));
  } catch (error) {
    console.error(`[ERROR] Virtual environment creation failed: ${error}`);
    throw error;
  }
  const venvCommand = pythonPath + ' -m venv ' + venvDir;
  console.log(`[INFO] Creating virtual environment: ${venvCommand}`);

  const venvProcess = spawn(pythonPath, ['-m', 'venv', venvDir]);
  venvProcess.stdout?.on(
      'data',
      (data: Buffer) => console.log(`[INFO] Venv stdout: ${data.toString()}`));

  venvProcess.stderr?.on(
      'data',
      (data: Buffer) =>
          console.error(`[ERROR] Venv stderr: ${data.toString()}`));

  venvProcess.on('error', (error) => {
    console.error(`[ERROR] Venv process error: ${error.message}`);
    throw error;
  });

  venvProcess.on('close', (code: number) => {
    if (code !== 0) {
      console.error(`[ERROR] Venv process exited with code ${code}`);
      throw new Error(`Venv process exited with code ${code}`);
    } else {
      console.log(`[INFO] Venv process exited successfully with code ${code}`);
    }
  });

  // wait for the virtual environment to be created
  await new Promise((resolve) => setTimeout(resolve, 5000));

  // verify the virtual environment was created
  try {
    await vscode.workspace.fs.stat(vscode.Uri.file(venvDir));

    if (process.platform === 'win32') {
      await vscode.workspace.fs.stat(vscode.Uri.file(venvPythonPathWin));
    } else {
      await vscode.workspace.fs.stat(vscode.Uri.file(venvPythonPathUnix));
    }

    var venvPath =
        process.platform === 'win32' ? venvPythonPathWin : venvPythonPathUnix;

    vscode.window.showInformationMessage(
        `Virtual environment created: ${venvPath}`);
    const requirementsPath = path.resolve(__dirname, '..', 'requirements.txt');
    await installRequirements(venvPath, requirementsPath);

    // wait for the requirements to be installed
    await new Promise((resolve) => setTimeout(resolve, 5000));

    vscode.window.showInformationMessage('Installed requirements successfully');
    return venvPath;
  } catch (error) {
    console.error(`[ERROR] Virtual environment creation failed: ${error}`);
    throw error;
  }
}

async function installRequirements(
    venvPath: string, requirementsPath: string): Promise<void> {
  const pipInstallCommand = venvPath + ' -m pip install -r ' + requirementsPath;

  console.log(`[INFO] Installing requirements: ${pipInstallCommand}`);

  const pipProcess =
      spawn(venvPath, ['-m', 'pip', 'install', '-r', requirementsPath]);
  pipProcess.stdout?.on(
      'data',
      (data: Buffer) => console.log(`[INFO] Pip stdout: ${data.toString()}`));

  pipProcess.stderr?.on(
      'data',
      (data: Buffer) =>
          console.error(`[ERROR] Pip stderr: ${data.toString()}`));

  return;
}

/**
 * Restart the Helix Language Server.
 * @param context The extension context.
 * @param helixPath The Helix compiler path.
 */
async function restartLanguageServer(
    context: vscode.ExtensionContext, helixPath: string): Promise<void> {
  try {
    if (client) {
      vscode.window.showInformationMessage('Stopping Helix Language Server...');
      await client.stop();
    }

    const helixPath =
        await getOrPromptHelixCompilerPath();  // points to helix/bin/helix
    if (!helixPath) {
      vscode.window.showErrorMessage(
          'Helix compiler path not set. Extension will be deactivated.');
      return;
    }

    const pythonPath = await findPython();
    if (!pythonPath) {
      vscode.window.showErrorMessage(
          'Python path not set. Extension will be deactivated.');
      return;
    }

    const venvPath =
        await createVirtualEnv(pythonPath, path.resolve(helixPath, '..', '..'));
    if (!venvPath) {
      vscode.window.showErrorMessage(
          'Virtual environment creation failed. Extension will be deactivated.');
      return;
    }

    const serverOptions = createServerOptions(helixPath, venvPath);
    const clientOptions = createClientOptions();

    client = new LanguageClient(
        'HelixVscodeLSP', 'Helix Language Support', serverOptions,
        clientOptions);

    vscode.window.showInformationMessage('Restarting Helix Language Server...');
    client.start();

    context.subscriptions.push(client);
  } catch (error) {
    vscode.window.showErrorMessage(
        `Failed to restart Helix Language Server: ${error}`);
    console.error(`[ERROR] Restart error: ${error}`);
  }
}

/**
 * Deactivate the extension
 */
export function deactivate(): Thenable<void>|undefined {
  if (!client) {
    return undefined;
  }
  vscode.window.showInformationMessage(
      'Deactivating Helix Language Server Client...');
  return client.stop();
}

/**
 * Get the Helix compiler path from VS Code settings or prompt the user if not
 * set.
 * @returns The Helix compiler path or `undefined` if the user cancels the
 *     input.
 */
async function getOrPromptHelixCompilerPath(): Promise<string> {
  const config = vscode.workspace.getConfiguration('helix');
  let helixPath: string|undefined = config.get<string>('compilerPath');
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
    vscode.window.showErrorMessage(
        `Helix compiler path does not exist or is not executable: ${
            helixPath}`);

    while (!helixPathValid) {
      helixPath = await vscode.window.showInputBox({
        prompt: 'Enter the full path to the Helix compiler (helix binary)',
        placeHolder: '/path/to/helix',
      });

      if (helixPath) {
        try {
          await vscode.workspace.fs.stat(vscode.Uri.file(helixPath));
          helixPathValid = true;
        } catch (error) {
          console.error(`[ERROR] Helix compiler path error: ${error}`);
          helixPath = '';
        }

        await config.update(
            'compilerPath', helixPath, vscode.ConfigurationTarget.Global);

        vscode.window.showInformationMessage(
            `Helix compiler path set to: ${helixPath}`);
      }

      // sleep for 4 seconds
      await new Promise((resolve) => setTimeout(resolve, 4000));
    }
  }

  return helixPath || '';
}

/**
 * Create server options for the language client.
 * @returns A promise that resolves with the StreamInfo object.
 */
function createServerOptions(helixPath: string, venvPath: string): () =>
    Promise<StreamInfo> {
  return (): Promise<StreamInfo> => {
    return new Promise((resolve, reject) => {
      const SERVER_SCRIPT_PATH = path.resolve(__dirname, '..', 'server', 'server.py');

      console.log(`[INFO] Server script path: ${SERVER_SCRIPT_PATH}`);
      console.log(`[INFO] Helix binary path: ${helixPath}`);

      const serverProcess: ChildProcess = spawn(
          venvPath, [SERVER_SCRIPT_PATH, helixPath],
          {stdio: ['pipe', 'pipe', 'pipe']});

      serverProcess.stdout?.on(
          'data',
          (data: Buffer) =>
              console.log(`[INFO] Server stdout: ${data.toString()}`));
      serverProcess.stderr?.on(
          'data',
          (data: Buffer) =>
              console.error(`[ERROR] Server stderr: ${data.toString()}`));
      serverProcess.on('error', (error) => {
        console.error(`[ERROR] Server process error: ${error.message}`);
        reject(error);
      });
      serverProcess.on('close', (code: number) => {
        if (code !== 0) {
          console.error(`[ERROR] Server process exited with code ${code}`);
          reject(new Error(`Server process exited with code ${code}`));
        } else {
          console.log(
              `[INFO] Server process exited successfully with code ${code}`);
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
    documentSelector: [{scheme: 'file', language: 'Helix'}],
    synchronize: {
      fileEvents: vscode.workspace.createFileSystemWatcher('**/*.hlx'),
    },
    outputChannel: vscode.window.createOutputChannel('Helix Language Server'),
  };
}