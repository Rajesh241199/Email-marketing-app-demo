import re
from typing import Optional, Sequence, List, Tuple
from sqlalchemy.orm import Session

from models.template import Template
from schemas.template import TemplateCreate, TemplateUpdate, TemplateValidationResult

# Merge field pattern: {{field_name}}
MERGE_FIELD_RE = re.compile(r"\{\{(\w+)\}\}")

REQUIRED_UNSUBSCRIBE_PATTERNS = [
    r"unsubscribe",
    r"\{\{unsubscribe_link\}\}",
    r"\{\{unsubscribe_url\}\}",
]


def get_template(db: Session, template_id: int) -> Optional[Template]:
    return db.query(Template).filter(Template.id == template_id).first()


def get_templates_by_account(
    db: Session,
    account_id: int,
    *,
    page: int = 1,
    per_page: int = 50,
    q: Optional[str] = None,
    include_archived: bool = False,
) -> Tuple[int, Sequence[Template]]:
    query = db.query(Template).filter(Template.account_id == account_id)
    if not include_archived:
        query = query.filter(Template.is_archived == False)
    if q:
        query = query.filter(Template.name.ilike(f"%{q}%"))
    total = query.count()
    items = query.order_by(Template.updated_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return total, items


def create_template(db: Session, account_id: int, data: TemplateCreate) -> Template:
    has_unsub, _ = _check_unsubscribe_link(data.body_html or "")
    template = Template(
        account_id=account_id,
        name=data.name,
        subject=data.subject,
        pre_header=data.pre_header,
        body_html=data.body_html,
        body_json=data.body_json,
        body_text=data.body_text,
        has_unsubscribe_link=has_unsub,
    )
    result = _validate(template)
    template.is_valid = result.is_valid
    template.validation_errors = result.errors if result.errors else None
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def update_template(db: Session, template_id: int, data: TemplateUpdate) -> Optional[Template]:
    template = get_template(db, template_id)
    if not template:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(template, key, value)
    if data.body_html is not None:
        template.has_unsubscribe_link, _ = _check_unsubscribe_link(data.body_html)
    result = _validate(template)
    template.is_valid = result.is_valid
    template.validation_errors = result.errors if result.errors else None
    db.commit()
    db.refresh(template)
    return template


def delete_template(db: Session, template_id: int) -> bool:
    template = get_template(db, template_id)
    if not template:
        return False
    db.delete(template)
    db.commit()
    return True


def duplicate_template(db: Session, template_id: int) -> Optional[Template]:
    original = get_template(db, template_id)
    if not original:
        return None
    copy = Template(
        account_id=original.account_id,
        name=f"Copy of {original.name}",
        subject=original.subject,
        pre_header=original.pre_header,
        body_html=original.body_html,
        body_json=original.body_json,
        body_text=original.body_text,
        has_unsubscribe_link=original.has_unsubscribe_link,
        is_valid=original.is_valid,
        validation_errors=original.validation_errors,
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return copy


def validate_template(db: Session, template_id: int) -> Optional[TemplateValidationResult]:
    template = get_template(db, template_id)
    if not template:
        return None
    result = _validate(template)
    template.is_valid = result.is_valid
    template.validation_errors = result.errors if result.errors else None
    template.has_unsubscribe_link, _ = _check_unsubscribe_link(template.body_html or "")
    db.commit()
    return result


def render_preview(template: Template, merge_data: dict) -> str:
    """Substitute {{field}} merge tags with provided values."""
    html = template.body_html or ""

    def replacer(match):
        field = match.group(1)
        return merge_data.get(field, match.group(0))

    return MERGE_FIELD_RE.sub(replacer, html)


# ── Validation ────────────────────────────────────────────────────────────────

def _validate(template: Template) -> TemplateValidationResult:
    errors: List[str] = []

    if not template.subject or not template.subject.strip():
        errors.append("Subject line is required.")

    body = template.body_html or ""
    if not body.strip():
        errors.append("Email body cannot be empty.")

    has_unsub, _ = _check_unsubscribe_link(body)
    if not has_unsub:
        errors.append("Email body must contain an unsubscribe link ({{unsubscribe_link}} or 'unsubscribe' text).")

    return TemplateValidationResult(is_valid=len(errors) == 0, errors=errors)


def _check_unsubscribe_link(html: str):
    for pattern in REQUIRED_UNSUBSCRIBE_PATTERNS:
        if re.search(pattern, html, re.IGNORECASE):
            return True, pattern
    return False, None
