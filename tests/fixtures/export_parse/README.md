# Export Parse Fixture Replay

This directory is for committed replay fixtures that are safe for unit tests.

Allowed here:

- Hand-written mock parsed JSON.
- Hand-written mock expected JSON.
- Minimal artificial OCR blocks with no real UID, account id, nickname, QR code payload, or image-derived raw dump.
- Small schema examples that exercise parser and evaluator behavior.

Not allowed here:

- Real official share images.
- Real `data/probes/parsed` or `data/probes/experiments` outputs.
- Real OCR `text_blocks` from a user image.
- UID, account id, cookie, token, stoken, ltoken, QR payload, or app/browser profile data.

Local, user-specific expected files belong under:

```text
data/probes/expected/
```

Local replay outputs belong under:

```text
data/probes/replay_batches/
```

Both are probe data and must stay out of Git.
