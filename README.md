# AloeDAV

A CalDAV and CardDAV library for Python, built so that an AI agent can maintain a
user's calendar, tasks and contacts *while the same user keeps syncing that data with
an ordinary client* — Apple Calendar, DAVx5, Thunderbird, Outlook.

That second half sets the project's first principle: **never destroy what you do not
understand.** The agent is not the only writer, so every edit it makes is a
read-modify-write against data some other client authored. Any property the model
fails to represent is a property the agent silently deletes on the user's behalf.
Fidelity therefore ranks above features — see [ROADMAP.md](ROADMAP.md).

> **Status:** the client, models and storage are usable; the DAV *server* is not built
> yet. See [ROADMAP.md](ROADMAP.md) for what is done and what is next.

## Install

```bash
pip install -e .
```

## Browser view

A read-only web view of whatever is in storage, useful for seeing what a client
actually wrote:

```bash
python -m aloedav.web --root ./data --demo
```

Then open <http://127.0.0.1:8000>. `--demo` seeds sample data, including a recurring
meeting with one instance moved and another excluded, across a daylight-saving
boundary.

## Storage

AloeDAV stores data through the `Store` interface, and ships two backends. **You do
not have to choose** — the default works, and the rest of this section only matters
if you want the other one.

| | Default: `aloelite` | Alternative: `file` |
|---|---|---|
| Layout | one portable `.sqlite` file | one `.ics`/`.vcf` per resource |
| Integrity | SQLite transactions | atomic write + rename |
| Encryption | optional (ChaCha20-Poly1305) | none |
| Readable with `ls` / `grep` | no | **yes** |
| Backup | copy one file | copy a directory tree |

The default is [Aloelite](https://github.com/Aloecraft-org/aloelite), a filesystem held
inside a single SQLite file. It gives real transactional integrity, one file to move or
back up, and optional encryption.

### If you want plain, browsable files

Some people would rather be able to open the data with any text editor — to see exactly
what a client wrote, to `grep` across a calendar, or to keep it in version control.
Use the filesystem backend:

```bash
python -m aloedav.web --root ./data --backend file
```

Resources then live at `./data/collections/<user>/<collection>/<uid>.ics`, exactly as
written on the wire, CRLF and all.

### Switching after you already have data

Both backends write the same tree, so you can move between them at any time in either
direction:

```bash
python -m aloedav.web migrate --root ./data --to file        # to plain files
python -m aloedav.web migrate --root ./data --to aloelite    # back again
```

Resources move as stored bytes — nothing is reparsed or rewritten on the way. The
source store is left in place so you can check the result before deleting it, and the
chosen backend is recorded, so ordinary runs afterwards use the one you migrated into
without needing `--backend` again.

### Encryption

Only the `aloelite` backend can encrypt. Encryption is decided once, when the volume is
created, and cannot be retrofitted:

```python
from aloedav.storage.backends import open_store

store = open_store("./data", pin=b"correct-horse-battery-staple")
```

Note that Aloelite encrypts file *contents*; paths, timestamps and tree structure stay
readable in the SQLite schema. For a calendar that means an observer without the PIN
still learns how many resources exist and when they changed. Put the file on an
encrypted volume if that matters.

## Library use

```python
from aloedav.client import AloeDAVClient

client = AloeDAVClient("https://dav.example.com", "user", "password")
resource = client.fetch_resource("work", "standup@example.com.ics")

# One resource, not one component: a recurring master and its RECURRENCE-ID
# overrides live together, so editing one instance does not destroy the series.
resource.master.summary = "Daily standup"
client.upsert_object("work", resource)
```

Recurrences expand into concrete instances, in the master's own timezone, so a 9am
New York meeting stays 9am across a daylight-saving change:

```python
from aloedav.model.m03_occurrence import expand

for occurrence in expand(resource, start=..., end=...):
    print(occurrence.start.to_wire(), occurrence.summary, occurrence.is_override)
```

## Tests

```bash
pytest
```

The storage contract runs unchanged against both backends, so a test that passes for
one and fails for the other has found a real divergence.

## License

See [LICENSE](LICENSE).
