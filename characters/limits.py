"""Numeric limits shared between the app and its documentation.

This module deliberately imports nothing. `docs/conf.py` reads these constants
to build the documentation, and a docs build has neither Django settings nor a
SECRET_KEY, so anything importable from here must stay dependency-free.
"""

# Ceiling on an uploaded character picture. Django's own upload limits govern
# only non-file POST data, so a file needs its own cap.
MAX_PICTURE_MB = 1
MAX_PICTURE_BYTES = MAX_PICTURE_MB * 1024 * 1024

# Ceiling on each side in pixels. Bytes alone don't bound the cost of decoding
# an image: a heavily compressed file well under MAX_PICTURE_BYTES can hold tens
# of thousands of pixels per side and expand to gigabytes in memory when Pillow
# opens it. Dimensions are read from the header, so this rejects such a file
# before anything decodes it.
MAX_PICTURE_PIXELS = 2048

# Ceiling on how many external-sync warnings are kept on a character and shown
# on the sheet. A page whose markup is broken wholesale can produce a warning
# per record, and neither the row nor the reader benefits from all of them:
# the first few say what went wrong, and the sheet reports how many were
# dropped.
MAX_SYNC_WARNINGS = 50
