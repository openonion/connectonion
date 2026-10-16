---
title: "The last button was disabled"
date: 2026-10-17
---

REM's source panel has a small search box for long originals. Until a query has several matches, “Next match” is disabled. That is a sensible state for the button, but the phone modal's keyboard loop still counted it as the last place focus could go.

The source inspection exposed the mismatch. Shift+Tab from Close selected the disabled button; Tab from the search field did not recognize that it had already reached the last usable control. The code was looping over visible controls rather than eligible keyboard stops.

The proposed patch filters disabled controls and negative tab stops before choosing those endpoints. It also keeps focus on the panel if none remain. The desktop panel stays nonmodal, and Escape still uses the existing close path.

Twelve isolated handler regressions pass after the fix. They do not prove native focus behavior. The browser tool rejected the local file preview by security policy, so no browser workaround or screenshots followed. A separate AI reviewer checked the code and agreed with the narrow change; the visual and assistive-technology review remains pending.

This stays a draft until manual browser evidence and required CI are available. The lesson is in that boundary too: a convincing unit check can justify a proposed fix, but it cannot stand in for seeing someone move through the actual interface.
