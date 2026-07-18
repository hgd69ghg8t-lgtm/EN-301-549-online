# Licence status of this directory

The PDF in this directory is the original ETSI EN 301 549 deliverable,
unchanged. It is **not** covered by the repository's MIT or CC BY 4.0
licences, and permission to reproduce and publish it has not yet been
obtained from ETSI — hosting and distributing this file must not be
treated as authorised until written permission has been received and
recorded. See [`../LICENSES.md`](../LICENSES.md).

This directory is the *source* copy. The build (`python3
scripts/build.py`) copies it into `docs/source/` so the PDF stays
published at its existing public URL (`source/en_301549v040100va.pdf`).
Never edit the PDF bytes; `data/source-metadata.json` records its
SHA-256 checksum and the build verifies it on every run.
