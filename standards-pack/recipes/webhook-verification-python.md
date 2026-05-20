# Python webhook verification — see the helper

The Python webhook verification helper ships inside this pack at
`sdk-helpers/python/`. See its `README.md` for usage examples and
the verification surface. The helper is pure standard library
(`hmac`, `hashlib`, `secrets`) — no `cryptography` package, no C
toolchain required.

A reference snippet is not duplicated here because the helper IS
the reference — `sbs_webhooks.py` is ~150 lines and reads as
documentation. See `sdk-helpers/python/README.md` for the
single-source-of-truth usage examples.
