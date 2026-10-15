# KoDex

KoDex is a personal launcher and workspace profile for this fork of OpenAI's Codex CLI. It is a community-maintained fork, not the official Codex desktop app. The upstream engine remains separately licensed under Apache-2.0; see the repository's `LICENSE` and `NOTICE` files.

## Windows setup

The upstream source currently supports Windows builds through WSL2. Install/build the engine using [`../docs/install.md`](../docs/install.md), then make its `codex.exe` available on Windows `PATH`. Start KoDex from PowerShell:

```powershell
& .\kodex\Start-KoDex.ps1
```

The launcher sets `CODEX_HOME` to `%LOCALAPPDATA%\KoDex`, keeping KoDex's configuration, sessions, and credentials separate from an existing Codex profile. Do not copy credentials between those profiles.

## Local model mode

Install and start a local model provider such as Ollama, download a model while online, then launch:

```powershell
& .\kodex\Start-KoDex.ps1 -LocalModel
```

`-LocalModel` passes the engine's `--oss` option. Configure the local provider in `%LOCALAPPDATA%\KoDex\config.toml` (for example `oss_provider = "ollama"`). Once the provider and model are installed locally, inference can run without an internet connection. Initial downloads, updates, external tools, and requests to cloud services still need a network; offline execution is not a guarantee that every feature is local.

With 8 GB RAM, begin with a small quantized model and short context. Larger models can be slow or fail to fit in memory. A local model has no provider token quota, but is limited by the laptop's memory, speed, disk space, and the provider/model license.

## Current scope

This first KoDex change establishes distinct branding, a separate profile, and a local-model launch path. It does not yet add JARVIS voice/task coordination, REA reverse-engineering tools, or FreeCAD/Arduino/VS Code automation. Those need separate integrations and local validation; FreeCAD was not detected on this laptop, while Arduino IDE and VS Code were found.
