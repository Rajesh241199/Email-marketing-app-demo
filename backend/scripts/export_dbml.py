"""Export the SQLAlchemy models to DBML for dbdiagram.io.

The models are the source of truth; this keeps docs/architecture/schema.dbml in sync.

    cd backend
    python -m scripts.export_dbml > ../docs/architecture/schema.dbml
"""

from __future__ import annotations

import sys

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import configure_mappers

from app.db.models import Base

GROUPS: dict[str, tuple[str, str]] = {
    # module          -> (TableGroup name, header colour)
    "accounts": ("account_and_auth", "#3D5FBF"),
    "auth": ("account_and_auth", "#3D5FBF"),
    "senders": ("account_and_auth", "#3D5FBF"),
    "subscribers": ("audience", "#0F8A83"),
    "segments": ("audience", "#0F8A83"),
    "suppressions": ("consent_and_suppression", "#C2410C"),
    "preferences": ("consent_and_suppression", "#C2410C"),
    "imports": ("csv_import", "#A87A0C"),
    "templates": ("templates_content", "#7650B8"),
    "campaigns": ("campaign_management", "#C4405F"),
    "analytics": ("delivery_and_analytics", "#2A7DB5"),
    "automations": ("automation", "#4F8A25"),
}

DIALECT = postgresql.dialect()


def q(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def col_type(col: sa.Column) -> str:
    if isinstance(col.type, sa.Enum):
        return col.type.name
    if isinstance(col.type, postgresql.ARRAY):
        return '"' + col.type.item_type.compile(dialect=DIALECT).lower() + '[]"'
    t = col.type.compile(dialect=DIALECT).lower()
    return {"timestamp with time zone": "timestamptz"}.get(t, t)


def default_expr(col: sa.Column) -> str | None:
    sd = col.server_default
    if sd is None or isinstance(sd, sa.Identity):
        return None
    arg = sd.arg
    if isinstance(arg, str):
        return arg if arg.lstrip("-").isdigit() else q(arg)
    sql = str(arg.compile(dialect=DIALECT))
    if sql in ("true", "false"):
        return sql
    return f"`{sql}`"


def main(out=sys.stdout) -> None:
    configure_mappers()
    md = Base.metadata
    w = out.write

    table_module: dict[str, str] = {}
    table_doc: dict[str, str] = {}
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        name = mapper.local_table.name
        table_module[name] = cls.__module__.split(".")[1]
        doc = (cls.__doc__ or "").strip()
        table_doc[name] = " ".join(doc.split("\n\n")[0].split())

    w("// Generated from the SQLAlchemy models by backend/scripts/export_dbml.py.\n")
    w("// Edit the models, not this file.\n\n")
    w("Project email_marketing_platform {\n  database_type: 'PostgreSQL'\n")
    w("  Note: 'Email Marketing Platform - Schema V1'\n}\n\n")

    enums: dict[str, list[str]] = {}
    for t in md.tables.values():
        for c in t.columns:
            if isinstance(c.type, sa.Enum):
                enums[c.type.name] = list(c.type.enums)
    for name, values in sorted(enums.items()):
        w(f"Enum {name} {{\n" + "".join(f"  {v}\n" for v in values) + "}\n\n")

    groups: dict[str, list[str]] = {}
    for t in md.sorted_tables:
        module = table_module.get(t.name, "")
        group, colour = GROUPS.get(module, ("other", "#6B7280"))
        groups.setdefault(group, []).append(t.name)
        pk_cols = [c.name for c in t.primary_key.columns]
        w(f"Table {t.name} [headercolor: {colour}] {{\n")
        for c in t.columns:
            s: list[str] = []
            if len(pk_cols) == 1 and c.name in pk_cols:
                s.append("pk")
            if c.identity is not None:
                s.append("increment")
            if not c.nullable and not (len(pk_cols) == 1 and c.name in pk_cols):
                s.append("not null")
            if c.unique:
                s.append("unique")
            d = default_expr(c)
            if d:
                s.append(f"default: {d}")
            for fk in c.foreign_keys:
                target = f"{fk.column.table.name}.{fk.column.name}"
                if c.primary_key and len(pk_cols) == 1:
                    op = "-"
                else:
                    op = ">" if not c.nullable else ">?"
                s.append(f"ref: {op} {target}")
            if c.comment:
                s.append(f"note: {q(c.comment)}")
            settings = f" [{', '.join(s)}]" if s else ""
            w(f"  {c.name} {col_type(c)}{settings}\n")

        index_lines: list[str] = []
        if len(pk_cols) > 1:
            index_lines.append(f"({', '.join(pk_cols)}) [pk]")
        for ix in sorted(t.indexes, key=lambda i: i.name or ""):
            cols = [c.name for c in ix.columns]
            target = cols[0] if len(cols) == 1 else f"({', '.join(cols)})"
            s = [f"name: {q(ix.name)}"]
            if ix.unique:
                s.insert(0, "unique")
            where = ix.dialect_options["postgresql"].get("where")
            if where is not None:
                s.append(f"note: {q('WHERE ' + str(where))}")
            index_lines.append(f"{target} [{', '.join(s)}]")
        if index_lines:
            w("\n  Indexes {\n" + "".join(f"    {line}\n" for line in index_lines) + "  }\n")

        notes = [table_doc.get(t.name, "")]
        checks = [c for c in t.constraints if isinstance(c, sa.CheckConstraint)]
        if checks:
            notes.append(
                "CHECK: " + " | ".join(f"{c.name}: {' '.join(str(c.sqltext).split())}" for c in checks)
            )
        note = " ".join(n for n in notes if n)
        if note:
            w(f"\n  Note: {q(note)}\n")
        w("}\n\n")

    for group, tables in groups.items():
        w(f"TableGroup {group} {{\n" + "".join(f"  {t}\n" for t in tables) + "}\n\n")


if __name__ == "__main__":
    main()
