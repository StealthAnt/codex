# Clicky source inspection

This note records a source-level inspection of the public [`farzaa/clicky`](https://github.com/farzaa/clicky) repository at commit `a80fa80721a8aebe51a170a7780705024ebc6e46` (main, inspected 2026-10-15). Clicky's README says the repository is the open-source version and that newer development is private; this inspection therefore describes only that public snapshot.

## What the public app does

- It is a macOS menu-bar assistant built in Swift/Xcode, with a small panel and a transparent overlay that can point near the cursor.
- Push-to-talk sends a transcript and screenshots of the user's displays to Claude. The assistant may answer with a `[POINT:x,y:label]` marker; Clicky maps the selected screen's image coordinates to the display and draws the pointer overlay.
- Voice uses AssemblyAI streaming transcription with an Apple Speech fallback, Claude for answers, and ElevenLabs for spoken output. A Cloudflare Worker proxies API calls and holds provider secrets outside the app binary.
- The public README lists macOS 14.2+, Xcode 15+, a Cloudflare account, and provider keys as setup requirements. It requests microphone, accessibility, and screen-recording permissions.

These observations come from the repository README, `CompanionManager.swift`, `OverlayWindow.swift`, transcription providers, and `worker/src/index.ts`. This is static source inspection; it does not establish behavior of the newer private Clicky app or prove that a built binary behaves the same way.

## KoDex adaptation

KoDex is a Windows desktop app, so the macOS ScreenCaptureKit and overlay implementation cannot be reused directly. This update adds a reviewable chat plan for complete file edits and a small allowlist of local app actions. It preserves a separate user approval before writing files and another before running supported FreeCAD, Arduino, MATLAB, or editor actions. REA is included as a separate local analysis engine; the current in-app REA analysis action targets JavaScript/Electron artifacts, not Clicky's Swift/Xcode source.

The open-source Clicky repository is MIT-licensed. KoDex does not copy its source files. See the repository for the original license and source: https://github.com/farzaa/clicky.
