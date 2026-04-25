import { ChildProcess, spawn, execFile } from "child_process";
import { Transform, TransformCallback } from "stream";
import * as path from "path";
import * as fs from "fs";
import * as vscode from "vscode";
import {
    LanguageClient,
    LanguageClientOptions,
    StreamInfo,
} from "vscode-languageclient/node";

let client: LanguageClient | undefined;
let outputChannel: vscode.OutputChannel;

function log(level: "info" | "warn" | "error", msg: string): void {
    const ts = new Date().toISOString();
    outputChannel.appendLine(`[${ts}] [${level}] ${msg}`);
}

// ─── activation ──────────────────────────────────────────────────────────────

export async function activate(
    context: vscode.ExtensionContext
): Promise<void> {
    outputChannel = vscode.window.createOutputChannel("Kairo Language Server");
    context.subscriptions.push(outputChannel);

    log("info", "extension activating…");
    log("info", `platform: ${process.platform}, arch: ${process.arch}`);
    log("info", `vscode version: ${vscode.version}`);
    log("info", `extension host PATH: ${process.env.PATH ?? "(empty)"}`);
    log("info", `SHELL env: ${process.env.SHELL ?? "(unset)"}`);

    context.subscriptions.push(
        vscode.commands.registerCommand("kairo.restartLSP", () =>
            startLanguageServer(context)
        )
    );

    await startLanguageServer(context);
}

export function deactivate(): Thenable<void> | undefined {
    log("info", "extension deactivating…");
    return client?.stop();
}

class LspTap extends Transform {
    private label: string;

    constructor(label: string) {
        super();
        this.label = label;
    }

    _transform(chunk: Buffer, _encoding: string, callback: TransformCallback): void {
        logLspMessages(this.label, chunk);
        callback(null, chunk); // pass through unchanged
    }
}

function logLspMessages(label: string, chunk: Buffer): void {
    const raw = chunk.toString("utf-8");
    // split on Content-Length headers to separate messages
    const messages = raw.split(/(?=Content-Length:)/);
    for (const msg of messages) {
        const trimmed = msg.trim();
        if (!trimmed) continue;

        // separate header from body
        const headerEnd = trimmed.indexOf("\r\n\r\n");
        if (headerEnd === -1) {
            log("info", `[${label}] (partial) ${trimmed.slice(0, 200)}`);
            continue;
        }

        const header = trimmed.slice(0, headerEnd);
        const body = trimmed.slice(headerEnd + 4);

        try {
            const json = JSON.parse(body);
            const method = json.method ?? "(response)";
            const id = json.id !== undefined ? ` id=${json.id}` : "";
            const error = json.error ? ` ERROR: ${JSON.stringify(json.error)}` : "";
            log("info", `[${label}] ${method}${id}${error}`);
            log("info", `[${label}] ${JSON.stringify(json, null, 2)}`);
        } catch {
            log("info", `[${label}] ${header} | body(${body.length} bytes): ${body.slice(0, 300)}`);
        }
    }
}

// ─── top-level server lifecycle ──────────────────────────────────────────────

async function startLanguageServer(
    context: vscode.ExtensionContext
): Promise<void> {
    try {
        if (client) {
            log("info", "stopping previous LSP instance…");
            await client.stop();
            client = undefined;
        }

        log("info", "=== resolving kairo compiler ===");
        const kairoPath = await resolveKairoPath();
        if (!kairoPath) return;
        log("info", `kairo resolved: ${kairoPath}`);

        const kairoRoot = path.resolve(path.dirname(kairoPath), "..");
        log("info", `kairo root: ${kairoRoot}`);

        log("info", "=== resolving LSP server script ===");
        const serverScript = await resolveServerScript(kairoRoot);
        if (!serverScript) return;
        log("info", `server script resolved: ${serverScript}`);

        log("info", "=== resolving python ===");
        const pythonPath = await resolvePython();
        if (!pythonPath) return;
        log("info", `python resolved: ${pythonPath}`);

        log("info", "=== ensuring venv ===");
        const venvPython = await ensureVenv(pythonPath, kairoRoot);
        if (!venvPython) return;
        log("info", `venv python resolved: ${venvPython}`);

        log("info", "=== starting LSP client ===");
        const serverOptions = makeServerOptions(venvPython, serverScript, kairoPath);
        const clientOptions = makeClientOptions();

        client = new LanguageClient(
            "KairoVscodeLSP",
            "Kairo Language Support",
            serverOptions,
            clientOptions
        );

        await client.start();
        log("info", "LSP client started successfully");
        context.subscriptions.push(client);
    } catch (err) {
        const msg = `Failed to start Kairo LSP: ${err}`;
        log("error", msg);
        vscode.window.showErrorMessage(msg);
    }
}

// ─── path resolution ─────────────────────────────────────────────────────────

async function resolveKairoPath(): Promise<string | undefined> {
    const config = vscode.workspace.getConfiguration("kairo");
    const configured = config.get<string>("path") ?? "";
    log("info", `kairo.path setting: "${configured}"`);

    if (configured && configured !== "kairo") {
        const exists = await fileExists(configured);
        log("info", `explicit path "${configured}" exists: ${exists}`);
        if (exists) return configured;
        vscode.window.showWarningMessage(
            `kairo.path "${configured}" not found, falling back to PATH lookup.`
        );
    }

    log("info", "attempting PATH lookup for 'kairo'…");
    const found = await whichBinary("kairo");
    if (found) {
        log("info", `found kairo on PATH: ${found}`);
        return found;
    }
    log("warn", "kairo not found on PATH (direct + login shell both failed)");

    const picked = await vscode.window.showInputBox({
        prompt: "Enter the full path to the kairo binary",
        placeHolder: "/path/to/kairo",
    });

    if (!picked) {
        log("warn", "user cancelled kairo path prompt");
        vscode.window.showErrorMessage(
            "Kairo compiler not found. Set kairo.path or add kairo to your PATH."
        );
        return undefined;
    }

    const pickedExists = await fileExists(picked);
    log("info", `user-provided path "${picked}" exists: ${pickedExists}`);
    if (!pickedExists) {
        vscode.window.showErrorMessage(
            "Kairo compiler not found. Set kairo.path or add kairo to your PATH."
        );
        return undefined;
    }

    await config.update("path", picked, vscode.ConfigurationTarget.Global);
    log("info", `saved kairo.path to global settings: ${picked}`);
    return picked;
}

async function resolveServerScript(
    kairoRoot: string
): Promise<string | undefined> {
    const config = vscode.workspace.getConfiguration("kairo");
    const configured = config.get<string>("serverPath") ?? "";
    log("info", `kairo.serverPath setting: "${configured}"`);

    if (configured && configured !== "kairo-lsp") {
        const exists = await fileExists(configured);
        log("info", `explicit serverPath "${configured}" exists: ${exists}`);
        if (exists) return configured;
        log("warn", "explicit serverPath not found, trying derived path");
    }

    const derived = path.join(kairoRoot, "scripts", "lsp-server.py");
    const derivedExists = await fileExists(derived);
    log("info", `derived server script "${derived}" exists: ${derivedExists}`);

    if (derivedExists) return derived;

    vscode.window.showErrorMessage(
        `LSP server script not found at ${derived}. Set kairo.serverPath manually.`
    );
    return undefined;
}

async function resolvePython(): Promise<string | undefined> {
    const config = vscode.workspace.getConfiguration("kairo");
    const configured = config.get<string>("pythonPath") ?? "";
    log("info", `kairo.pythonPath setting: "${configured}"`);

    if (configured && configured !== "python") {
        const exists = await fileExists(configured);
        log("info", `explicit pythonPath "${configured}" exists: ${exists}`);
        if (exists) return configured;
        vscode.window.showWarningMessage(
            `kairo.pythonPath "${configured}" not found, falling back to PATH.`
        );
    }

    for (const name of ["python3", "python"]) {
        log("info", `attempting PATH lookup for '${name}'…`);
        const found = await whichBinary(name);
        if (found) {
            log("info", `found ${name}: ${found}`);
            return found;
        }
        log("info", `${name} not found on PATH`);
    }

    vscode.window.showErrorMessage(
        "Python not found. Install Python 3 or set kairo.pythonPath."
    );
    return undefined;
}

// ─── venv management ─────────────────────────────────────────────────────────

async function ensureVenv(
    pythonPath: string,
    kairoRoot: string
): Promise<string | undefined> {
    const venvDir = path.join(kairoRoot, ".kairo-lsp-venv");
    const venvPython =
        process.platform === "win32"
            ? path.join(venvDir, "Scripts", "python.exe")
            : path.join(venvDir, "bin", "python");

    log("info", `venv dir: ${venvDir}`);
    log("info", `expected venv python: ${venvPython}`);

    if (await fileExists(venvPython)) {
        log("info", "venv already exists, reusing");
        return venvPython;
    }

    log("info", `creating venv: ${pythonPath} -m venv ${venvDir}`);
    try {
        await runProcess(pythonPath, ["-m", "venv", venvDir]);
        log("info", "venv created successfully");
    } catch (err) {
        log("error", `venv creation failed: ${err}`);
        vscode.window.showErrorMessage(`venv creation failed: ${err}`);
        return undefined;
    }

    if (!(await fileExists(venvPython))) {
        log("error", `venv created but interpreter missing at ${venvPython}`);
        vscode.window.showErrorMessage(
            `venv created but python not found at ${venvPython}`
        );
        return undefined;
    }

    const reqFile = path.join(kairoRoot, "scripts", "requirements.txt");
    const reqExists = await fileExists(reqFile);
    log("info", `requirements.txt at "${reqFile}" exists: ${reqExists}`);

    if (reqExists) {
        log("info", `installing: ${venvPython} -m pip install -q -r ${reqFile}`);
        try {
            await runProcess(venvPython, ["-m", "pip", "install", "-q", "-r", reqFile]);
            log("info", "requirements installed successfully");
        } catch (err) {
            log("error", `pip install failed: ${err}`);
            vscode.window.showErrorMessage(`pip install failed: ${err}`);
            return undefined;
        }
    }

    return venvPython;
}

// ─── LSP client wiring ──────────────────────────────────────────────────────

function makeServerOptions(
    venvPython: string,
    serverScript: string,
    kairoPath: string
): () => Promise<StreamInfo> {
    return () =>
        new Promise((resolve, reject) => {
            log("info", `spawning LSP server: ${venvPython} ${serverScript} ${kairoPath}`);

            const proc: ChildProcess = spawn(venvPython, [serverScript, kairoPath], {
                stdio: ["pipe", "pipe", "pipe"],
            });

            log("info", `server process PID: ${proc.pid ?? "unknown"}`);

            proc.stderr?.on("data", (chunk: Buffer) => {
                const lines = chunk.toString().trimEnd().split(/\r?\n/);
                for (const line of lines) {
                    log("info", `[server stderr] ${line}`);
                }
            });

            proc.on("error", (err) => {
                log("error", `server process error: ${err.message}`);
                reject(err);
            });

            proc.on("close", (code) => {
                log("info", `server process exited (code ${code})`);
            });

            const writerTap = new LspTap("client → server");
            writerTap.pipe(proc.stdin!);

            const readerTap = new LspTap("server → client");
            proc.stdout!.pipe(readerTap);

            resolve({
                writer: writerTap,
                reader: readerTap,
            });
        });
}

function makeClientOptions(): LanguageClientOptions {
    return {
        documentSelector: [{ scheme: "file", language: "kairo" }],
        outputChannel,
    };
}

// ─── utilities ───────────────────────────────────────────────────────────────

function fileExists(p: string): Promise<boolean> {
    return fs.promises
        .access(p, fs.constants.F_OK)
        .then(() => true)
        .catch(() => false);
}

async function whichBinary(name: string): Promise<string | undefined> {
    const cmd = process.platform === "win32" ? "where" : "which";

    log("info", `whichBinary("${name}"): trying direct: ${cmd} ${name}`);
    const direct = await tryExecFile(cmd, [name]);
    if (direct) {
        log("info", `whichBinary("${name}"): direct hit: ${direct}`);
        return direct;
    }
    log("info", `whichBinary("${name}"): direct miss`);

    if (process.platform !== "win32") {
        const shell = process.env.SHELL || "/bin/sh";
        const isFish = shell.endsWith("/fish");
        const args = isFish
            ? ["-l", "-i", "-c", `which ${name}`]
            : ["-lic", `which ${name}`];

        log("info", `whichBinary("${name}"): trying interactive login shell: ${shell} ${JSON.stringify(args)}`);
        const result = await tryExecFile(shell, args);
        if (result) {
            log("info", `whichBinary("${name}"): shell hit: ${result}`);
        } else {
            log("info", `whichBinary("${name}"): shell miss`);
        }
        return result;
    }

    return undefined;
}

function tryExecFile(cmd: string, args: string[]): Promise<string | undefined> {
    return new Promise((resolve) => {
        execFile(cmd, args, { timeout: 5000 }, (err, stdout, stderr) => {
            const lines = (stdout ?? "").trim().split(/\r?\n/).filter(l => l.trim());
            const lastLine = lines.length ? lines[lines.length - 1].trim() : "";

            if (lastLine && lastLine.startsWith("/")) {
                log("info", `tryExecFile(${cmd} ${args.join(" ")}): → ${lastLine}`);
                resolve(lastLine);
            } else {
                const reason = err ? err.message : "no valid path in stdout";
                log("info", `tryExecFile(${cmd} ${args.join(" ")}): miss (${reason})`);
                resolve(undefined);
            }
        });
    });
}

function runProcess(cmd: string, args: string[]): Promise<void> {
    return new Promise((resolve, reject) => {
        log("info", `runProcess: ${cmd} ${args.join(" ")}`);
        const proc = spawn(cmd, args, { stdio: ["ignore", "pipe", "pipe"] });

        let stderr = "";
        proc.stderr?.on("data", (chunk: Buffer) => {
            stderr += chunk.toString();
        });

        proc.on("error", (err) => {
            log("error", `runProcess error: ${err.message}`);
            reject(err);
        });
        proc.on("close", (code) => {
            log("info", `runProcess exited (code ${code})${stderr ? ` stderr: ${stderr.slice(0, 300)}` : ""}`);
            if (code === 0) resolve();
            else reject(new Error(`${cmd} exited ${code}: ${stderr.slice(0, 500)}`));
        });
    });
}


