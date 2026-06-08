"""Package scanner for Knowledge Ingestion Phase 1.2.

Scans a knowledge package directory, validates document frontmatter
against the package metadata contract, and returns a dry-run report.

No database writes. No file modifications. No embeddings.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from modules.knowledge_ingestion.schemas import (
    DOCUMENT_TYPES,
    SCOPE_TYPES,
    SOURCE_TYPES,
    SUPPORTED_LOCALES,
    VISIBILITY_LEVELS,
    DocumentValidationIssue,
    PackageMetadata,
    PackageScanRequest,
    PackageScanResult,
    ParsedKnowledgeDocument,
)

DEFAULT_WORKER_CODE = "knowledge_ingestion_worker"


def load_package_metadata(package_root: str) -> PackageMetadata:
    root = Path(package_root)
    profile_path = root / "_metadata" / "package-profile.yaml"
    scope_path = root / "_metadata" / "knowledge-scope-mapping.yaml"
    tags_path = root / "_metadata" / "access-tags.yaml"

    profile: dict[str, Any] = {}
    if profile_path.exists():
        with open(profile_path, encoding="utf-8") as f:
            profile = yaml.safe_load(f) or {}

    scope_mapping: dict[str, Any] = {}
    if scope_path.exists():
        with open(scope_path, encoding="utf-8") as f:
            scope_mapping = yaml.safe_load(f) or {}

    access_tags: dict[str, Any] = {"tags": []}
    if tags_path.exists():
        with open(tags_path, encoding="utf-8") as f:
            access_tags = yaml.safe_load(f) or {"tags": []}

    return PackageMetadata(
        package_profile=profile,
        scope_mapping=scope_mapping,
        access_tags=access_tags,
    )


def _known_access_tag_set(pkg_meta: PackageMetadata) -> set[str]:
    tags = pkg_meta.access_tags
    if isinstance(tags, dict):
        raw = tags.get("tags", [])
        if isinstance(raw, list):
            return {t.get("tag", "") for t in raw if isinstance(t, dict)}
    return set()


def _allowed_areas(pkg_meta: PackageMetadata) -> dict[str, list[str]]:
    areas = pkg_meta.scope_mapping.get("allowed_areas", {})
    if isinstance(areas, dict):
        return areas
    return {}


def _normalize_locale(raw: str) -> str:
    parts = raw.split("-")
    return parts[0]


def _parse_frontmatter(file_path: Path) -> tuple[bool, dict[str, Any] | None]:
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return False, None

    if not content.startswith("---"):
        return False, None

    parts = content.split("---", 2)
    if len(parts) < 3:
        return False, None

    yaml_block = parts[1]
    try:
        data = yaml.safe_load(yaml_block)
    except yaml.YAMLError:
        return False, None

    if not isinstance(data, dict):
        return False, None

    return True, data


def _validate_document_frontmatter(
    relative_path: str,
    frontmatter: dict[str, Any] | None,
    pkg_meta: PackageMetadata,
) -> tuple[bool, bool, list[DocumentValidationIssue]]:
    issues: list[DocumentValidationIssue] = []
    valid = True
    candidate = False

    if frontmatter is None:
        issues.append(DocumentValidationIssue(
            path=relative_path,
            field="frontmatter",
            message="Missing or invalid YAML frontmatter",
            severity="error",
        ))
        return False, False, issues

    status_val = frontmatter.get("status", "")
    ingestion_status_val = frontmatter.get("ingestion_status", "")

    if status_val in ("", None):
        issues.append(DocumentValidationIssue(
            path=relative_path,
            field="status",
            message="status is required in document frontmatter",
            severity="error",
        ))
        valid = False

    if ingestion_status_val in ("", None):
        issues.append(DocumentValidationIssue(
            path=relative_path,
            field="ingestion_status",
            message="ingestion_status is required in document frontmatter",
            severity="error",
        ))
        valid = False

    is_draft_status = status_val == "draft"
    is_not_ready = ingestion_status_val == "not_ready"

    if status_val and status_val not in ("draft", "active", "approved", "deprecated", "archived"):
        issues.append(DocumentValidationIssue(
            path=relative_path,
            field="status",
            message=f"Unknown status value: {status_val!r}",
            severity="warning",
        ))

    if ingestion_status_val and ingestion_status_val not in (
        "not_ready", "ready", "approved_for_ingestion", "deprecated"
    ):
        issues.append(DocumentValidationIssue(
            path=relative_path,
            field="ingestion_status",
            message=f"Unknown ingestion_status value: {ingestion_status_val!r}",
            severity="warning",
        ))

    candidate = not is_draft_status and not is_not_ready

    document_type = frontmatter.get("document_type", "")
    if document_type and document_type not in DOCUMENT_TYPES:
        issues.append(DocumentValidationIssue(
            path=relative_path,
            field="document_type",
            message=f"document_type must be one of {sorted(DOCUMENT_TYPES)}, got {document_type!r}",
            severity="error",
        ))
        valid = False

    area_key = frontmatter.get("area_key", "")
    if area_key:
        if "/" in area_key:
            issues.append(DocumentValidationIssue(
                path=relative_path,
                field="area_key",
                message="area_key must not contain '/'",
                severity="error",
            ))
            valid = False
        allowed_areas = _allowed_areas(pkg_meta)
        if allowed_areas and area_key not in allowed_areas:
            issues.append(DocumentValidationIssue(
                path=relative_path,
                field="area_key",
                message=f"area_key {area_key!r} not in allowed_areas: {list(allowed_areas)}",
                severity="warning",
            ))

    topic_key = frontmatter.get("topic_key", "")
    if topic_key and "/" in topic_key:
        issues.append(DocumentValidationIssue(
            path=relative_path,
            field="topic_key",
            message="topic_key must not contain '/'",
            severity="error",
        ))
        valid = False

    node_path = frontmatter.get("node_path", "")
    if node_path:
        if not node_path.startswith("/"):
            issues.append(DocumentValidationIssue(
                path=relative_path,
                field="node_path",
                message="node_path must start with '/'",
                severity="error",
            ))
            valid = False
        elif node_path != "/" and node_path.endswith("/"):
            issues.append(DocumentValidationIssue(
                path=relative_path,
                field="node_path",
                message="node_path must not end with '/' (except root '/')",
                severity="error",
            ))
            valid = False

    access_tags_list = frontmatter.get("access_tags", [])
    known_tags = _known_access_tag_set(pkg_meta)
    if not access_tags_list:
        issues.append(DocumentValidationIssue(
            path=relative_path,
            field="access_tags",
            message="access_tags must not be empty",
            severity="error",
        ))
        valid = False
    else:
        if known_tags:
            for tag in access_tags_list:
                if tag not in known_tags:
                    issues.append(DocumentValidationIssue(
                        path=relative_path,
                        field="access_tags",
                        message=f"Unknown access_tag {tag!r}; known: {sorted(known_tags)}",
                        severity="error",
                    ))
                    valid = False

    locale_raw = frontmatter.get("locale", frontmatter.get("language", ""))
    if locale_raw:
        normalized = _normalize_locale(locale_raw)
        if normalized not in SUPPORTED_LOCALES:
            issues.append(DocumentValidationIssue(
                path=relative_path,
                field="locale",
                message=f"locale must be one of {sorted(SUPPORTED_LOCALES)}, got {locale_raw!r}",
                severity="error",
            ))
            valid = False

    scope_type = frontmatter.get("scope_type", "")
    if scope_type and scope_type not in SCOPE_TYPES:
        issues.append(DocumentValidationIssue(
            path=relative_path,
            field="scope_type",
            message=f"scope_type must be one of {sorted(SCOPE_TYPES)}, got {scope_type!r}",
            severity="error",
        ))
        valid = False

    visibility_val = frontmatter.get("visibility", "")
    if visibility_val and visibility_val not in VISIBILITY_LEVELS:
        issues.append(DocumentValidationIssue(
            path=relative_path,
            field="visibility",
            message=f"visibility must be one of {sorted(VISIBILITY_LEVELS)}, got {visibility_val!r}",
            severity="error",
        ))
        valid = False

    source_type = frontmatter.get("source_type", "")
    if source_type and source_type not in SOURCE_TYPES:
        issues.append(DocumentValidationIssue(
            path=relative_path,
            field="source_type",
            message=f"source_type must be one of {sorted(SOURCE_TYPES)}, got {source_type!r}",
            severity="error",
        ))
        valid = False

    doc_package_code = frontmatter.get("package_code", "")
    expected_package_code = pkg_meta.package_profile.get("package_code", "")
    if doc_package_code and expected_package_code and doc_package_code != expected_package_code:
        issues.append(DocumentValidationIssue(
            path=relative_path,
            field="package_code",
            message=f"package_code mismatch: frontmatter {doc_package_code!r} != expected {expected_package_code!r}",
            severity="error",
        ))
        valid = False

    doc_knowledge_scope = frontmatter.get("knowledge_scope_code", "")
    expected_scope = pkg_meta.scope_mapping.get("knowledge_scope_code", "")
    if doc_knowledge_scope and expected_scope and doc_knowledge_scope != expected_scope:
        issues.append(DocumentValidationIssue(
            path=relative_path,
            field="knowledge_scope_code",
            message=(
                f"knowledge_scope_code mismatch: frontmatter {doc_knowledge_scope!r} "
                f"!= expected {expected_scope!r}"
            ),
            severity="warning",
        ))

    doc_workspace = frontmatter.get("workspace_code", "")
    expected_workspace = pkg_meta.scope_mapping.get("workspace_code", "")
    if doc_workspace and expected_workspace and doc_workspace != expected_workspace:
        issues.append(DocumentValidationIssue(
            path=relative_path,
            field="workspace_code",
            message=(
                f"workspace_code mismatch: frontmatter {doc_workspace!r} "
                f"!= expected {expected_workspace!r} (from knowledge-scope-mapping)"
            ),
            severity="warning",
        ))

    return valid, candidate, issues


class KnowledgePackageScanner:
    """Scans a knowledge package directory and validates documents.

    No database writes. No file modifications. No embeddings.
    """

    def scan(
        self,
        request: PackageScanRequest,
    ) -> PackageScanResult:
        pkg_meta = load_package_metadata(request.package_root)
        warnings: list[str] = []
        errors: list[str] = []
        documents: list[ParsedKnowledgeDocument] = []
        scanned = 0
        valid = 0
        invalid = 0
        candidate = 0
        skipped = 0

        root = Path(request.package_root)
        approved_dir = root / "approved"
        drafts_dir = root / "drafts"

        if not approved_dir.is_dir():
            errors.append(f"approved/ directory not found: {approved_dir}")

        if request.include_drafts and not request.dry_run and not request.experimental:
            errors.append(
                "include_drafts=True requires dry_run=True or experimental=True"
            )

        if errors:
            return PackageScanResult(
                package_code=request.package_code,
                package_root=request.package_root,
                scanned_count=0,
                valid_count=0,
                invalid_count=0,
                candidate_count=0,
                skipped_count=0,
                documents=[],
                warnings=warnings,
                errors=errors,
            )

        for doc_file in sorted(approved_dir.rglob("*.md")):
            if doc_file.name == "README.md":
                continue
            rel = str(doc_file.relative_to(root))
            has_fm, fm = _parse_frontmatter(doc_file)
            is_valid, is_candidate, issues = _validate_document_frontmatter(
                rel, fm, pkg_meta,
            )
            scanned += 1
            if is_valid:
                valid += 1
            else:
                invalid += 1
            if is_candidate:
                candidate += 1
            documents.append(ParsedKnowledgeDocument(
                path=doc_file,
                relative_path=rel,
                source_section="approved",
                has_frontmatter=has_fm,
                frontmatter=fm,
                valid=is_valid,
                candidate_for_ingestion=is_candidate,
                issues=issues,
            ))

        if request.include_drafts and (request.dry_run or request.experimental):
            for doc_file in sorted(drafts_dir.rglob("*.md")):
                if doc_file.name == "README.md":
                    continue
                rel = str(doc_file.relative_to(root))
                has_fm, fm = _parse_frontmatter(doc_file)
                is_valid, is_candidate, issues = _validate_document_frontmatter(
                    rel, fm, pkg_meta,
                )
                scanned += 1
                if is_valid:
                    valid += 1
                else:
                    invalid += 1
                if is_candidate:
                    candidate += 1
                else:
                    skipped += 1
                documents.append(ParsedKnowledgeDocument(
                    path=doc_file,
                    relative_path=rel,
                    source_section="drafts",
                    has_frontmatter=has_fm,
                    frontmatter=fm,
                    valid=is_valid,
                    candidate_for_ingestion=is_candidate,
                    issues=issues,
                ))
        elif request.include_drafts:
            skipped_drafts = len([
                p for p in drafts_dir.rglob("*.md") if p.name != "README.md"
            ])
            skipped += skipped_drafts
        elif drafts_dir.is_dir():
            skipped_drafts = len([
                p for p in drafts_dir.rglob("*.md") if p.name != "README.md"
            ])
            skipped += skipped_drafts

        if not errors and not documents:
            warnings.append(
                f"No .md documents found in {request.package_root}/approved/"
            )

        return PackageScanResult(
            package_code=request.package_code,
            package_root=request.package_root,
            scanned_count=scanned,
            valid_count=valid,
            invalid_count=invalid,
            candidate_count=candidate,
            skipped_count=skipped,
            documents=documents,
            warnings=warnings,
            errors=errors,
        )
