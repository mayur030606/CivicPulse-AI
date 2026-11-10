"""Administrative account CLI.

Usage (run from ``backend/``):

    python -m app.cli create-admin --email admin@example.org
    python -m app.cli update-admin --current-email admin@example.org --new-email new@example.org

Passwords are read interactively with ``getpass`` and never printed, logged or
supplied as a command-line argument. ``create-admin`` refuses to run when an
administrator already exists, so there is no default/bootstrap credential.
``update-admin`` updates one existing administrator and never creates another.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.security import PasswordPolicyError
from app.database import SessionLocal
from app.models.enums import UserRole
from app.models.user import User
from app.services import auth as auth_service


def create_admin(email: str) -> int:
    try:
        with SessionLocal() as db:
            admin_count = db.scalar(
                select(func.count())
                .select_from(User)
                .where(User.role == UserRole.admin.value)
            )
            if admin_count:
                print(
                    "An administrator already exists. The bootstrap command is one-time only.",
                    file=sys.stderr,
                )
                return 1

            password = getpass.getpass("New administrator password: ")
            confirmation = getpass.getpass("Confirm password: ")
            if password != confirmation:
                print("Passwords do not match.", file=sys.stderr)
                return 1

            user = auth_service.create_user(
                db,
                email=email,
                password=password,
                role=UserRole.admin,
            )
            print(f"Administrator created: {user.email}")
            return 0
    except (PasswordPolicyError, auth_service.InvalidEmailError) as exc:
        print(f"Could not create administrator: {exc}", file=sys.stderr)
        return 1
    except auth_service.EmailAlreadyExistsError as exc:
        print(f"Could not create administrator: {exc}", file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print(
            "Could not access the users table. Run `alembic upgrade head` first.",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130


def update_admin(current_email: str, new_email: str) -> int:
    try:
        with SessionLocal() as db:
            password = getpass.getpass("New administrator password: ")
            confirmation = getpass.getpass("Confirm password: ")
            if password != confirmation:
                print("Passwords do not match.", file=sys.stderr)
                return 1

            auth_service.update_admin_credentials(
                db,
                current_email=current_email,
                new_email=new_email,
                new_password=password,
            )
            print("Administrator credentials updated.")
            return 0
    except (
        PasswordPolicyError,
        auth_service.InvalidEmailError,
        auth_service.EmailAlreadyExistsError,
        auth_service.AdminAccountError,
    ) as exc:
        print(f"Could not update administrator: {exc}", file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print(
            "Could not access the users table. Run `alembic upgrade head` first.",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="CivicPulse AI administrative account commands.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    create_admin_parser = subcommands.add_parser(
        "create-admin",
        help="Create the first administrator account interactively.",
    )
    create_admin_parser.add_argument(
        "--email",
        required=True,
        help="Email address for the first administrator.",
    )

    update_admin_parser = subcommands.add_parser(
        "update-admin",
        help="Update an existing administrator's email and password interactively.",
    )
    update_admin_parser.add_argument(
        "--current-email",
        required=True,
        help="Current email address of the administrator.",
    )
    update_admin_parser.add_argument(
        "--new-email",
        required=True,
        help="New email address for the administrator.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "create-admin":
        return create_admin(args.email)
    if args.command == "update-admin":
        return update_admin(args.current_email, args.new_email)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
