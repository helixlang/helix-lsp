# Kairo LSP Extension for Visual Studio Code

The Kairo LSP extension provides language server protocol (LSP) support for the Kairo programming language in Visual Studio Code. This extension enables features such as syntax highlighting, autocompletion, and error checking for Kairo files.

⚠️ **Warning**: This extension is **very unstable**. While it works to some extent, expect frequent issues and crashes, memory leaks and other issues. Stability improvements are planned with the introduction of a self-hosted compiler, but it does work for the most part.

## Features
- Basic syntax highlighting for Kairo files
- Autocompletion (limited support)
- Error diagnostics (experimental)
- Language server integration with Kairo

## Prerequisites
- Visual Studio Code (version 1.94.0 or higher)
- Python 3.8+ (required for the language server)
- [Kairo language binaries](https://github.com/kairolang/kairo-lang/releases) installed on your system
- Git (to clone and set up the extension)

## Installation
1. Clone this repository:
   ```bash
   git clone https://github.com/kairolang/kairo-lsp.git
   ```
2. Navigate to the extension directory:
   ```bash
   cd kairo-lsp
   ```
3. Install the required dependencies:
   ```bash
   npm install
   ```
4. Build the extension:
   ```bash
   npm run build --omit=dev
   ```
5. Pack the extension:
   ```bash
   vsce package
   ```
6. Install the extension in VS Code:
    - Open VS Code.
    - Go to `Extensions` (`Ctrl+Shift+X` or `Cmd+Shift+X` on macOS).
    - Click the "..." menu and select "Install from VSIX".
    - Locate the `.vsix` file in the `kairo-lsp` directory and install it.
    - Reload VS Code to activate the extension.
- Alternatively, you can install the extension from the [Visual Studio Marketplace](#) once it's published.
- Or, use `code --install-extension kairo-language-x.x.x.vsix` (make sure the path is correct) to install the extension from the command line.

## Configuration
Before opening any Kairo files in VS Code, you **must configure the extension manually**. Failing to do so will result in the LSP failing to initialize.

### Steps
1. **Locate the Extension**:
   - On **Windows**: `%USERPROFILE%\.vscode\extensions\kairo-language-x.x.x`
   - On **macOS/Linux**: `~/.vscode/extensions/kairo-language-x.x.x`

2. **Run the Configuration Script**:
   - Inside the extension folder, find the `config.py` script, in the extension's root directory. (or in the root of the source code).
  
   - Run the script:
     ```bash
     python config.py
     ```
   - When prompted, provide:
     - The full path to the Kairo binary (e.g., `<your-kairo-install-dir>/bin/kairo`)

3. **Verify the Output**:
   - The scrip outputs `json` to the console with contents similar to this:
     ```json
     {
         "kairo.path": "/path/to/your/kairo/bin/kairo",
         "kairo.pythonPath": "/path/to/your/python",
         "kairo.serverPath": "/path/to/kairo-lsp/server/server.py"
     }
     ```
   - Ensure the paths match your system setup.

4. **Add Settings to VS Code**:
   - Open VS Code settings:
     - **User Settings**: For all projects (recommended for single Kairo setups).
     - **Workspace Settings**: For project-specific configurations.
   - Add the generated JSON content to `settings.json`:
     - Go to `File > Preferences > Settings` (or `Code > Preferences > Settings` on macOS).
     - Search for "Edit in settings.json" and click the link.
     - Paste the JSON block under the existing configuration.
   - Example:
     ```json
     {
         "editor.tabSize": 4,
         "kairo.path": "/path/to/your/kairo/bin/kairo",
         "kairo.pythonPath": "/path/to/your/python",
         "kairo.serverPath": "/path/to/kairo-lsp/server/server.py"
     }
     ```

5. **Restart VS Code**:
   - Close and reopen VS Code to apply the settings.

6. **Test the LSP**:
   - Open a `.kro` file. If configured correctly, the LSP should initialize, and basic language features should work.

## Usage
- Open any `.kro` file in VS Code.
- The extension should automatically start the language server using the configured paths.
- Look for diagnostics in the Problems panel (`Ctrl+Shift+M` or `Cmd+Shift+M` on macOS).

## Troubleshooting
- **LSP Doesn't Start**: Ensure all paths in `settings.json` are correct and accessible. Check the VS Code Output panel (`View > Output`) for errors from "Kairo LSP".
- **Crashes or Freezes**: This is expected due to instability. Restart VS Code and try again.
- **No Features Working**: Verify the Kairo binary and Python paths are executable. Run `kairo --version` and `python --version` in your terminal to test.
- **Still Broken?**: Open an issue on the [GitHub repository](https://github.com/kairolang/kairo-lsp.git) with logs from the Output panel.

## Known Issues
- Frequent crashes due to unstable integration with the Kairo compiler.
- Limited autocompletion and diagnostic accuracy.
- Self-hosted compiler (future update) will resolve many of these problems.

## Contributing
We welcome contributions! Please:
1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/xyz`).
3. Submit a pull request with detailed descriptions of changes.

## Future Plans
- Replace the current unstable backend with a self-hosted Kairo compiler.
- Improve LSP stability and feature set.
- Add support for more advanced IDE features (e.g., debugging).

## License
This project is licensed under the [MIT License](LICENSE).

## Support
For bugs or feature requests, open an issue on the [GitHub repository](https://github.com/kairolang/kairo-lsp.git). Include your `settings.json` (with sensitive paths redacted) and any relevant logs.



FIX:

Failed to activate Kairo Language Server Client: CodeExpectedError: Unable to write to User Settings because kairo.path is not a registered configuration.