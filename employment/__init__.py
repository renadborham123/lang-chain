"""Local-first employment operating system domain package.

Repository exports are lazy so importing model metadata for Alembic never
opens the application repository or runs ``create_all`` ahead of migrations.
"""

from .database import init_database

__all__ = ["EmploymentRepository", "init_database", "repository"]


def __getattr__(name: str):
    if name in {"EmploymentRepository", "repository"}:
        from .repository import EmploymentRepository, repository

        return {"EmploymentRepository": EmploymentRepository, "repository": repository}[name]
    raise AttributeError(name)
