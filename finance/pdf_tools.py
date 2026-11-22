"""Open, unlock and split statement PDFs.

In plain English:
1. Fingerprint: a unique code for the file, so the same PDF is never processed twice.
2. Unlock: try the password you typed, then any saved in the macOS Keychain.
   This happens on your laptop; passwords are never sent anywhere.
3. Split: cut the PDF into small groups of pages, each an unlocked mini-PDF in memory.
"""

from __future__ import annotations

import base64
import hashlib
import io
from pathlib import Path

import keyring
from keyring.errors import KeyringError, PasswordDeleteError
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

KEYCHAIN_SERVICE = "where-did-my-money-go"
_INDEX = "__saved_password_names__"  # Keychain entry listing the names you've saved


class WrongPassword(Exception):
    """The PDF is locked and none of the passwords opened it."""


class BadPdf(Exception):
    """The file isn't a readable PDF."""


def fingerprint(path: Path) -> str:
    """SHA-256 of the file's bytes: same file → same fingerprint, even if renamed."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ── Saved passwords (macOS Keychain) ─────────────────────────────────────────


def saved_password_names() -> list[str]:
    try:
        raw = keyring.get_password(KEYCHAIN_SERVICE, _INDEX) or ""
    except KeyringError:
        return []
    return [n for n in raw.split("\n") if n]


def save_password(name: str, password: str) -> None:
    name = name.strip()
    if not name or name == _INDEX:
        raise ValueError("Give the password a short name, like 'mainbank'.")
    keyring.set_password(KEYCHAIN_SERVICE, name, password)
    names = saved_password_names()
    if name not in names:
        keyring.set_password(KEYCHAIN_SERVICE, _INDEX, "\n".join(names + [name]))


def remove_password(name: str) -> bool:
    try:
        keyring.delete_password(KEYCHAIN_SERVICE, name)
        removed = True
    except PasswordDeleteError:
        removed = False
    names = [n for n in saved_password_names() if n != name]
    keyring.set_password(KEYCHAIN_SERVICE, _INDEX, "\n".join(names))
    return removed


def _saved_passwords() -> list[str]:
    passwords = []
    for name in saved_password_names():
        try:
            secret = keyring.get_password(KEYCHAIN_SERVICE, name)
        except KeyringError:
            secret = None
        if secret:
            passwords.append(secret)
    return passwords


# ── Opening and splitting ────────────────────────────────────────────────────


def open_pdf(path: Path, password: str | None = None) -> PdfReader:
    """Open a PDF, unlocking it with the typed password or any saved one."""
    try:
        reader = PdfReader(path)
    except (PdfReadError, ValueError, OSError) as e:
        raise BadPdf(f"{Path(path).name} isn't a readable PDF.") from e
    if not reader.is_encrypted:
        return reader

    candidates = ([password] if password else []) + _saved_passwords()
    for candidate in candidates:
        reader = PdfReader(path)  # fresh reader for each attempt
        try:
            if reader.decrypt(candidate):  # PasswordType.NOT_DECRYPTED (0) means "no"
                return reader
        except (PdfReadError, NotImplementedError):
            continue
    raise WrongPassword(Path(path).name)


def page_groups(reader: PdfReader, size: int) -> list[range]:
    """[range(0, 3), range(3, 6), …]: page numbers to send together."""
    total = len(reader.pages)
    return [range(start, min(start + size, total)) for start in range(0, total, size)]


def pages_as_pdf(reader: PdfReader, pages: range) -> str:
    """Copy some pages into a new, unlocked mini-PDF and return it as base64 text."""
    writer = PdfWriter()
    for i in pages:
        writer.add_page(reader.pages[i])
    buffer = io.BytesIO()
    writer.write(buffer)
    return base64.standard_b64encode(buffer.getvalue()).decode()
