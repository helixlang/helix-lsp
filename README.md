# Kairo Language Support for Visual Studio Code

Language server protocol (LSP) support for [Kairo](https://kairolang.org),
providing real-time diagnostics, syntax highlighting, and editor integration.

## Features

- Syntax highlighting for `.kro` and `.kairo` files
- Real-time error and warning diagnostics from the Kairo compiler
- Hover information and go-to-definition (via clangd proxy)
- Automatic compiler discovery from PATH
- Automatic Python venv management for the language server

## Getting Started

1. Install the [Kairo compiler](https://kairolang.org/install) and
   ensure `kairo` is available on your PATH.
2. Install this extension from the
   [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=KSF.kairo).
3. Open a `.kro` file the language server starts automatically.

Python 3.8+ must be available on your system. The extension will
find it automatically; no manual configuration is needed.

## Configuration

All settings are optional. The extension auto-discovers paths when possible.

| Setting | Default | Description |
|---|---|---|
| `kairo.path` | `kairo` | Path to the Kairo compiler binary. Leave as `kairo` to auto-detect from PATH. |
| `kairo.pythonPath` | `python` | Path to Python 3. Leave as `python` to auto-detect. |
| `kairo.serverPath` | (auto) | Path to the LSP server script. Derived from the compiler location by default. |

## Commands

- **Kairo: Restart Language Server** restart the LSP if it gets
  into a bad state (`Ctrl+Shift+P` → "kairo: Restart Language Server")

## Building from Source

```bash
git clone https://github.com/kairolang/kairo-lsp.git
cd kairo-lsp
npm install
npm run build
vsce package
```

Then install the `.vsix` via Extensions → "..." → "Install from VSIX".

## Status

This extension is under active development alongside the Kairo compiler.
Some features are still stabilizing if you run into issues, restart
the language server or [file a bug](https://github.com/kairolang/kairo-lsp/issues).