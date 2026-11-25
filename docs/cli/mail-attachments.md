# Agent mail attachments

Requires a backend with `/api/v1/email/send-with-attachments` and authenticated attachment endpoints. Files are sent to that capability endpoint so older servers fail visibly instead of silently dropping files.

```bash
co email attachments 123
co email download 123 456 --to ./orders
co email attachment-text 123 456 --to ./read-orders
co email raw 123 --output ./original.eml
co email send buyer@example.com 'Purchase order' 'Attached.' --attach ./po.pdf --attach ./lines.csv
co email reply 123 'Here is the revised file.' --attach ./revised.pdf
co email forward 123 ops@example.com 'Please review.'
co email attachments 789 --sent
co email download 789 1011 --sent --to ./sent-files
```

Forward includes the original files; `--without-attachments` explicitly omits them. Reply does not repeat the original files but accepts new `--attach` files. Failed sends print a retry using the same send ID and file paths. On a failed forward, its downloaded originals are retained in the printed private temporary directory so that retry remains possible. Successful forwards remove those temporary copies.

At most 100 files and 20 MiB total can be sent. Download commands verify size and SHA256, sanitize filenames on Windows/macOS/Linux and refuse to overwrite a file or symlink. `--to` is a directory. Each download includes inline files as well as ordinary attachments. Read/list/download do not mark email read.

```python
from connectonion import (
    get_email, get_email_attachments, download_email_attachment,
    read_email_attachment, download_raw_email, send_email,
)

email = get_email(123)  # includes attachment metadata
files = get_email_attachments(123)
saved = download_email_attachment(123, files[0]['id'], './originals')
# Choose a different directory when downloading the same filename again.
source = read_email_attachment(123, files[0]['id'], './readable-originals')
if source['readable']:
    print(source['text'])
else:
    print(source['error'])

result = send_email('buyer@example.com', 'Purchase order', 'Attached.',
                    attachments=['./po.pdf'], idempotency_key='purchase-order-123')
```

`read_email_attachment` retains the original and uses the existing framework document reader. PDF/Word/text are readable when text is available; optional XLSX support uses the `rem` extra. Scans without extractable text, unsupported formats, parser errors and truncated text are explicitly reported as unreadable. No OCR is claimed. Images/binary files can still be downloaded exactly.

The backend retains incoming raw MIME and decoded file bytes in PostgreSQL. An agent downloads a local copy only when asked. Historical attachments discarded by the previous receiver cannot be recovered by upgrading. Changing, adding or removing a file under the same send ID is rejected; retry an uncertain send with its original files and ID. Existing send budgets and mailbox ownership/read grants still apply.
