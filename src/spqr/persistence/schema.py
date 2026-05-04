"""Persistence schema versioning.

Bump SCHEMA_VERSION whenever the GameState shape changes incompatibly. Older
saves should fail loudly; migration is a future-milestone problem and not
worth doing speculatively in MVP."""

SCHEMA_VERSION = 13
