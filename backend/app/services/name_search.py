from sqlalchemy import ColumnElement, and_, func, or_

from app.models.user import User


def flexible_name_filter(query: str, *, include_email: bool = True) -> ColumnElement[bool]:
    """A "search by name" box should find someone whether the admin types
    just a first or last name, or both together ("Иван Петров") — a plain
    ILIKE of the whole query against a single column only ever matches the
    single-word case, since neither first_name nor last_name individually
    contains a two-word string.

    Splits the query on whitespace: a single word matches first name OR
    last name OR (optionally) email, same as before; multiple words require
    every word to appear somewhere across the full name (first + last, in
    either order — "Иван Петров" and "Петров Иван" both match), since a
    multi-word query can't sensibly be an email anyway.
    """
    words = query.split()
    if len(words) <= 1:
        clauses = [User.first_name.ilike(f"%{query}%"), User.last_name.ilike(f"%{query}%")]
        if include_email:
            clauses.append(User.email.ilike(f"%{query}%"))
        return or_(*clauses)

    full_name = func.concat(User.first_name, " ", User.last_name)
    return and_(*(full_name.ilike(f"%{word}%") for word in words))
