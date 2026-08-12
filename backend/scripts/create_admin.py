"""Creates (or updates) an admin panel login.

Passwords are read from stdin, never from argv - argv is visible to other
processes via `ps` and lands in shell history.

    python -m scripts.create_admin admin@example.com
    python -m scripts.create_admin admin@example.com --payouts

--payouts grants the separate payouts permission ARCHITECTURE.md §5
requires for reading payout records (IBANs); omit it for general staff.
"""

import getpass
import sys

from sqlmodel import Session, select

from app.core.security import hash_password
from app.db.session import engine
from app.models.admin_user import AdminUser

MIN_PASSWORD_LENGTH = 12


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        sys.exit(1)
    email = args[0].strip().lower()
    can_view_payouts = "--payouts" in sys.argv

    password = getpass.getpass("Password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
        sys.exit(1)
    if password != getpass.getpass("Confirm password: "):
        print("Passwords do not match.")
        sys.exit(1)

    with Session(engine) as session:
        existing = session.exec(select(AdminUser).where(AdminUser.email == email)).first()
        if existing:
            existing.hashed_password = hash_password(password)
            existing.can_view_payouts = can_view_payouts
            existing.is_active = True
            session.add(existing)
            action = "updated"
        else:
            session.add(
                AdminUser(
                    email=email,
                    hashed_password=hash_password(password),
                    can_view_payouts=can_view_payouts,
                )
            )
            action = "created"
        session.commit()

    print(f"Admin {action}: {email} (payouts permission: {can_view_payouts})")


if __name__ == "__main__":
    main()
