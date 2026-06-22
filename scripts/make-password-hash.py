#!/usr/bin/env python3
from __future__ import annotations

import getpass
import sys
from werkzeug.security import generate_password_hash


def main() -> None:
    if len(sys.argv) > 1:
        password = sys.argv[1]
    else:
        password = getpass.getpass("Dashboard password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            raise SystemExit("Passwords do not match")
    if len(password) < 12:
        raise SystemExit("Use at least 12 characters. Humanity has suffered enough weak passwords.")
    print(generate_password_hash(password, method="pbkdf2:sha256", salt_length=16))


if __name__ == "__main__":
    main()
