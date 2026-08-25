---
title: "An image prefix is not an image"
date: 2026-08-25
author: ConnectOnion Team
---

A browser inspection returned JSON containing the beginning of an image data
URL. The script had shortened the DOM attribute for readability, but the image
formatter treated any matching base64 substring as a complete screenshot. Its
decoder raised `Incorrect padding` from the `after_tools` hook and ended the
whole agent run. An informational DOM excerpt had become a fatal image upload.

Catching that one decoder exception would have hidden only the first symptom.
A truncated payload can still have valid padding, and arbitrary long text can
be made entirely from base64 characters. A minimum-length rule has the same
problem: it measures size, not whether an image is complete.

The formatter now accepts a candidate only after strict base64 decoding and
format-aware completeness checks. PNG, JPEG, GIF, and WebP each need their real
file signature and terminal structure. A malformed or truncated candidate is
left untouched as ordinary tool output. A genuine image continues to upload to
oo-api, and a real network or HTTP failure still fails loudly rather than
silently putting a large payload back into model history.

Regression coverage uses the exact truncated prefix that killed the production
LinkedIn run, plus base64 text that decodes successfully but is not an image.
Both now pass through without calling the uploader, while complete images still
exercise the unit and plugin end-to-end paths.

The extra validation is format-specific, so a newly supported image format must
add its own completeness rule. We would revisit this boundary if image results
move to a typed tool-result envelope where the producer supplies verified bytes
instead of asking a text scanner to infer intent.
