<!--
name: 'Tool Description: request_teach_access (part of teach mode)'
description: Describes a tool that requests permission to guide the user through a task step-by-step using fullscreen tooltip overlays instead of direct access
ccVersion: 2.1.84
-->
Request permission to guide the user through a task step-by-step with on-screen tooltips. Use this INSTEAD OF request_access when the user wants to LEARN how to do something (phrases like "teach me", "walk me through", "show me how", "help me learn"). On approval the main Claude window hides and a fullscreen tooltip overlay appears. You then call teach_step repeatedly; each call shows one tooltip and waits for the user to click Next. Same app-allowlist semantics as request_access, but no clipboard/system-key flags. Teach mode ends automatically when your turn ends.
