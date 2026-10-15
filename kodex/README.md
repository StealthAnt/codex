# KoDex

KoDex is a personal launcher and workspace profile for this fork of OpenAI's Codex CLI. It is a community-maintained fork, distinct from the official Codex desktop app. The upstream engine remains separately licensed; see the repository's `LICENSE` and `NOTICE` files.

## Windows setup

Build or install the engine using [`../docs/install.md`](../docs/install.md), then make its `codex.exe` available on Windows `PATH`. Start KoDex from PowerShell:

```powershell
& .\kodex\Start-KoDex.ps1
```

The launcher keeps configuration and sessions in `%LOCALAPPDATA%\KoDex`. On first launch, it adds a local MCP bridge entry to KoDex's `config.toml` if one does not already exist. Each bridge tool call uses the `prompt` approval mode. Existing configuration is preserved.

Python 3 is needed for the bridge. It uses only the Python standard library, communicates over local standard input/output, and does not open a network port.

## Standalone desktop MVP

The Windows build is at `kodex\dist\KoDex.exe`. Run it directly, or rebuild from source with `Start-KoDex-Desktop.ps1`:

```powershell
& .\kodex\Start-KoDex-Desktop.ps1
```

This Windows desktop UI is separate from the official Codex app. It includes local Ollama chat, optional ChatGPT access through the signed-in Codex CLI, Claude and Qwen API backends, a Claude Code CLI adapter, approved project folders, a task list, engineering app launch buttons, MathWorks project links, and the brain-network-with-light icon. The packaged executable includes its Python runtime. Chat works offline when Ollama is running and its model has already been downloaded.

ChatGPT uses the installed Codex CLI account session, runs in an ephemeral session, and starts with read-only sandbox access. Claude API and Qwen API require their own provider keys; KoDex encrypts saved keys with Windows DPAPI for the signed-in Windows account. Cloud requests send the current conversation to that provider and may be billed or limited under the provider's account. Qwen API keys are region-bound, so its base URL must match the key. Claude Code uses the installed `claude` CLI and its own OAuth sign-in in plan mode; it is unavailable until that CLI is installed. API keys are entered inside KoDex and are never requested in chat.

The Workspace page grants selected folders and lets the user attach UTF-8 text files up to 200 KB. ChatGPT and Claude Code are limited to read-only mode in the current desktop shell; KoDex does not yet apply generated edits or run commands from chat. Voice task coordination remains available through `Start-KoDexVoice.ps1`, but is not integrated into the desktop chat yet. The REA tools available to the coding session are not bundled in KoDex.

## Laptop integrations

KoDex can list the engineering integrations it recognizes and the apps registered in the current Windows Start menu. It can open a discovered app by exact display name. Initial task tools cover local task add/list/complete, opening VS Code, Arduino IDE, FreeCAD, and MATLAB, creating a basic FreeCAD box, compiling an Arduino sketch, and running an existing MATLAB `.m` file. Arduino compile does not upload firmware.

MATLAB actions use the MATLAB installation and license already configured on this Windows account. Sign in to MATLAB yourself in its desktop app if needed; KoDex does not collect or store MathWorks credentials. You can work with MATLAB Drive files if they are available through the signed-in app or a local synchronized folder. See MathWorks' [MATLAB batch mode documentation](https://www.mathworks.com/help/matlab/ref/matlabwindows.html) and [MATLAB Drive file access guide](https://www.mathworks.com/help/matlab/matlab_env/access-files-on-matlab-drive.html).

The read-only app catalog may show many apps, but discovery does not grant broad access to them. KoDex exposes an app action only when there is a defined integration or when you ask it to open an exact Start menu entry. Review and approve each tool call. Cloud apps still require their own account sign-in and network access.

## GitHub engineering resources

KoDex can search public GitHub repositories by robotics, engineering, STEAM, competitions, competition robots, Arduino, CAD/STL, MATLAB, or ROS. Results show links, descriptions, stars, recent activity, topics, and license labels. Search needs internet access and uses GitHub's unauthenticated API; GitHub applies rate limits, with search endpoints more restrictive than general API requests. KoDex caches results locally for 15 minutes. Private repositories are not accessed.

After reviewing a result, you can approve a separate action to clone that public repository into `%LOCALAPPDATA%\KoDex\resources`. KoDex can then list STL, STEP/STP, FCStd, SCAD, OBJ, 3MF, and IGES files in those local copies. It does not run downloaded scripts or open CAD/mesh assets automatically. Review the repository, license, and design before using it in a project or competition. See GitHub's [REST API rate limit documentation](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api).

## Voice task helper

Run `kodex\Start-KoDexVoice.ps1` to use push-to-talk task coordination. Press Enter, speak “add task …” or “list my tasks,” and the helper saves or reads tasks locally. It does not continuously listen. Windows speech recognition and microphone permission are required; availability depends on installed Windows language components.

## Local model mode

Install and start a local model provider such as Ollama, download a model while online, then launch:

```powershell
& .\kodex\Start-KoDex.ps1 -LocalModel
```

`-LocalModel` passes the engine's `--oss` option. Configure the local provider in `%LOCALAPPDATA%\KoDex\config.toml` (for example `oss_provider = "ollama"`). Once the provider and model are installed locally, inference can run without an internet connection. Initial downloads, updates, external tools, and cloud apps still need a network. With 8 GB RAM, begin with a small quantized model; speed and context length depend on memory and the provider/model license.
