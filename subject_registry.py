"""Single source of truth for H3 subjects used by continuity extraction.

The registry is deliberately a small dict-backed mapping.  H3 already has
stable ``<Subject N>`` identifiers and a persisted ``subject_registry_state``;
this module gives DINO/InsightFace and the H3 code one shared representation
of those records instead of maintaining separate subject models.
"""

from __future__ import annotations

import os
import re
from typing import Any, Callable, Iterable, Mapping, Optional

from PIL import Image


def _query_for_gender(gender: Any, fallback: str = "person") -> str:
    normalized = str(gender or "").strip().casefold()
    if normalized in {"female", "woman", "girl"}:
        return "woman"
    if normalized in {"male", "man", "boy"}:
        return "man"
    return fallback


_HUMAN_TYPES = frozenset({
    "human", "humans", "person", "people", "man", "men", "boy", "boys",
    "woman", "women", "girl", "girls",
})

_DINO_PROVENANCE_MARKERS = frozenset({
    "lore-defined",
    "story-defined",
    "picture-defined",
    "video-defined",
    "generated-defined",
})
_DINO_PROVENANCE_MARKER_RE = re.compile(
    r"(?i)\b(?:lore|story|picture|video|generated)-defined\b"
)
_DINO_REFERENCE_METADATA_RE = re.compile(
    r"(?i),?\s*(?:referenced in|continued from)\s+"
    r"<(?:Picture|Video)\s+\d+>"
)

def _normalize_query_rules(rules: Mapping[Any, Any] | None) -> dict[str, str]:
    return {
        str(phrase).strip().casefold(): str(query).strip()
        for phrase, query in (rules or {}).items()
        if str(phrase).strip() and str(query).strip()
    }


def _query_rule_match(text: Any, rules: Mapping[str, str]) -> Optional[str]:
    haystack = str(text or "").casefold()
    for phrase, query in rules.items():
        if re.search(
            rf"(?<![\w-]){re.escape(phrase)}(?![\w-])",
            haystack,
        ):
            return query
    return None


def _is_provenance_marker(value: Any) -> bool:
    normalized = re.sub(r"[_\s]+", "-", str(value or "").strip().casefold())
    return normalized in _DINO_PROVENANCE_MARKERS


def _contains_provenance_marker(value: Any) -> bool:
    return _DINO_PROVENANCE_MARKER_RE.search(str(value or "")) is not None


def _semantic_query_input(definition: Any, name: Any) -> str:
    """Return subject identity/description without provenance metadata."""

    canonical_name = str(name or "").strip()
    source = str(definition or "").strip()
    subject_body = source
    prefix = re.match(
        r"(?is)^\s*<Subject\s+\d+>\s+is\s+",
        subject_body,
    )
    if prefix:
        subject_body = subject_body[prefix.end():].strip()

    # These clauses identify where a definition came from; they do not tell
    # DINO what the subject is. Remove them before invoking the LLM resolver.
    subject_body = _DINO_REFERENCE_METADATA_RE.sub("", subject_body)
    subject_body = _DINO_PROVENANCE_MARKER_RE.sub("", subject_body)
    subject_body = re.sub(r"\s*,\s*(?=\.|$)", "", subject_body)
    subject_body = re.sub(r"\s+\.", ".", subject_body).strip(" .,:;")

    if not canonical_name:
        return subject_body
    if not subject_body:
        return canonical_name

    # Parser output normally begins with the canonical subject name. Keep the
    # name explicit and retain only any real description that follows it.
    if subject_body.casefold().startswith(canonical_name.casefold()):
        remainder = subject_body[len(canonical_name):].strip(" ,:;.")
        return (
            f"{canonical_name}, {remainder}"
            if remainder
            else canonical_name
        )
    return canonical_name


def _query_from_definition(line: str, name: str, gender: Any) -> Optional[str]:
    """Resolve only the tiny generic human normalization layer."""

    gender_query = _query_for_gender(gender, fallback="")
    if gender_query:
        return gender_query

    # In the established H3 format, the text after the subject name commonly
    # starts with the descriptive noun phrase: ``Amy, a young woman ...``.
    descriptor = re.search(
        r"(?i),\s*((?:a|an|the)\s+[^,.]+)",
        line,
    )
    phrase = descriptor.group(1) if descriptor else ""
    if not phrase and re.match(r"(?i)^(?:a|an|the)\s+", name.strip()):
        phrase = name
    if not phrase:
        # A bare proper name does not provide enough information for the
        # generic inference layer. Let the configured resolver classify it
        # before falling back to the generic ``person`` query.
        return None
    tokens = re.findall(r"[A-Za-z][A-Za-z'-]*", phrase.casefold())
    return "person" if any(token in _HUMAN_TYPES for token in tokens) else None


def _normalize_llm_query(value: Any) -> str:
    if isinstance(value, Mapping):
        value = value.get("query") or value.get("dino_query") or ""
    tokens = re.findall(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", str(value or ""))
    return "-".join(tokens[:2]).casefold()


def _print_dino_query_resolution(
    *,
    user_override: bool,
    builtin_normalization: bool,
    semantic_input: str,
) -> None:
    print(
        "DINO query resolver:\n"
        f"user override?         {'yes' if user_override else 'no'}\n"
        f"tiny built-in normalization?         "
        f"{'yes' if builtin_normalization else 'no'}\n"
        f'semantic input = "{semantic_input}"',
        flush=True,
    )

def _resolve_dino_query(
    explicit: Any,
    definition: Any,
    name: Any,
    gender: Any,
    user_rules: Mapping[Any, Any] | None = None,
    query_resolver: Optional[Callable[[str], Any]] = None,
) -> str:
    """Resolve one query once, in the registry's documented priority order."""

    text = _semantic_query_input(definition, name)
    configured = _query_rule_match(text, _normalize_query_rules(user_rules))
    configured = (
        configured
        if configured and not _contains_provenance_marker(configured)
        else None
    )
    normalized = _query_from_definition(text, str(name or ""), gender)
    _print_dino_query_resolution(
        user_override=(
            explicit is not None and str(explicit).strip() != ""
        ) or configured is not None,
        builtin_normalization=normalized is not None,
        semantic_input=text,
    )

    if explicit is not None and str(explicit).strip():
        return str(explicit)
    if configured:
        return configured
    if normalized:
        return normalized
    if query_resolver is not None:
        resolved = _normalize_llm_query(query_resolver(text))
        if resolved and not _contains_provenance_marker(resolved):
            return resolved
        # A resolver must not be able to turn provenance metadata into the
        # semantic query. The canonical name remains the safest fallback.
        fallback = _normalize_llm_query(str(name or ""))
        if fallback and not _contains_provenance_marker(fallback):
            return fallback
    return "person"


def _safe_name(value: Any) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    return safe.strip("._") or "subject"


def _infer_gender(text: str) -> str:
    if re.search(r"(?i)\b(?:male|man|boy|he|him)\b", text):
        return "male"
    if re.search(r"(?i)\b(?:female|woman|girl|she|her)\b", text):
        return "female"
    return "N/A"


class SubjectRegistry(dict):
    """A dict-backed registry with stable-ID and continuity helpers.

    Mapping keys remain compatible with the existing H3 code: parsed
    definitions use numeric Subject IDs and persisted continuity records use
    their existing subject names.  Every value carries the stable
    ``subject_id`` so either representation resolves to the same subject.
    """

    def __init__(
        self,
        *args: Any,
        query_rules: Mapping[Any, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.query_rules = _normalize_query_rules(query_rules)

    def register(
        self,
        subject_id: Any,
        *,
        name: Optional[str] = None,
        canonical_reference: Any = None,
        current_state_reference: Any = None,
        dino_query: Optional[str] = None,
        identity_backend: str = "insightface",
        registry_key: Any = None,
        definition: Any = None,
        query_rules: Mapping[Any, Any] | None = None,
        query_resolver: Optional[Callable[[str], Any]] = None,
        **metadata: Any,
    ) -> dict[str, Any]:
        """Register or replace one subject, preserving its stable ID."""

        if subject_id is None or not str(subject_id).strip():
            raise ValueError("subject_id must not be empty")
        stable_id = subject_id
        key = subject_id if registry_key is None else registry_key
        for existing_key, existing in self.items():
            if existing_key != key and str(existing.get("subject_id")) == str(stable_id):
                raise ValueError(f"Duplicate subject ID: {stable_id}")
        record = dict(metadata)
        explicit_query = dino_query is not None and str(dino_query).strip() != ""
        resolved_query = _resolve_dino_query(
            dino_query,
            definition,
            name if name is not None else metadata.get("name") or key,
            metadata.get("gender"),
            query_rules if query_rules is not None else self.query_rules,
            query_resolver,
        )
        record.update({
            "subject_id": stable_id,
            "name": str(name if name is not None else metadata.get("name") or key),
            "canonical_reference": canonical_reference,
            "current_state_reference": current_state_reference,
            "dino_query": resolved_query,
            "identity_backend": str(identity_backend or "insightface").strip()
            or "insightface",
            "dino_query_explicit": explicit_query,
        })
        if definition is not None:
            record["subject_definition"] = str(definition)
        self[key] = record
        return record

    @classmethod
    def from_records(
        cls,
        records: Mapping[Any, Mapping[str, Any]] | None,
        *,
        query_rules: Mapping[Any, Any] | None = None,
        query_resolver: Optional[Callable[[str], Any]] = None,
    ) -> "SubjectRegistry":
        """Adapt existing H3 continuity records without redefining subjects."""

        registry = cls(query_rules=query_rules)
        seen_ids: set[str] = set()
        for key, source in (records or {}).items():
            if not isinstance(source, Mapping):
                continue
            # Existing H3 continuity records are already the authoritative
            # records. Share mutable dicts in place so adapting them does not
            # create a second in-memory subject record.
            data = source if isinstance(source, dict) else dict(source)
            stable_id = data.get("subject_id", key)
            stable_key = str(stable_id)
            if stable_key in seen_ids:
                raise ValueError(f"Duplicate subject ID: {stable_id}")
            seen_ids.add(stable_key)
            canonical = data.get("canonical_reference") or data.get(
                "identity_reference"
            )
            current = data.get("current_state_reference")
            name = data.get("name") or key
            stored_query = data.get("dino_query")
            stored_query_explicit = bool(data.get("dino_query_explicit", False))
            # Auto-resolved legacy records may contain a provenance marker from
            # the old resolver bug. Re-resolve that invalid value, while valid
            # stored queries remain authoritative and are not inferred again.
            query_input = (
                None
                if (
                    stored_query
                    and not stored_query_explicit
                    and _is_provenance_marker(stored_query)
                )
                else stored_query
            )
            query = _resolve_dino_query(
                query_input,
                data.get("subject_definition") or data.get("definition") or name,
                name,
                data.get("gender"),
                query_rules if query_rules is not None else registry.query_rules,
                query_resolver,
            )
            backend = data.get("identity_backend") or "insightface"
            data.update({
                "subject_id": stable_id,
                "name": str(name),
                "canonical_reference": canonical,
                "current_state_reference": current,
                "dino_query": query,
                "identity_backend": str(backend).strip() or "insightface",
                "dino_query_explicit": data.get(
                    "dino_query_explicit",
                    data.get("dino_query") is not None,
                ),
            })
            registry[key] = data
        return registry

    @classmethod
    def from_definitions(
        cls,
        subject_definitions: Any,
        *,
        query_rules: Mapping[Any, Any] | None = None,
        query_resolver: Optional[Callable[[str], Any]] = None,
        stored_records: Mapping[Any, Mapping[str, Any]] | None = None,
    ) -> "SubjectRegistry":
        """Parse H3 definitions, reusing persisted DINO queries when present.

        ``stored_records`` is the continuity-state subject mapping.  A stored
        query is authoritative for an existing subject, so parsing a subject
        definition does not ask the LLM again.  Subjects without a stored
        query (normally newly created subjects) still go through the normal
        resolver path.
        """

        registry = cls(query_rules=query_rules)
        lines = [
            line.strip()
            for line in str(subject_definitions or "").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        for line in lines:
            match = re.match(
                r"(?i)^\s*<Subject\s+(?P<subject>\d+)>\s+is\s+"
                r"(?P<name>[A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*)*?)\s*"
                r"(?=,|\(\s*S\d+\s*\)\s*\.?\s*$|\.?\s*$)",
                line,
            )
            if match is None:
                match = re.match(
                    r"(?i)^\s*(?:<\s*)?Picture\s+(?P<picture>\d+)\s*"
                    r"(?:>\s*)?(?:\(from\s+Shot\s+\d+\)\s+)?is\s+"
                    r"(?P<name>[A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*)*)"
                    r"(?:\s+and\s+aligns\s+with\s+the\s+\d+(?:\.\d+)?-second\s+"
                    r"mark\s+of\s+the\s+target\s+video)?\.\s*$",
                    line,
                )
                if match is not None:
                    subject_id = int(match.group("picture"))
                    name = match.group("name").strip()
                    picture_ids = [subject_id]
                    speaker_id = f"S{subject_id}"
            else:
                subject_id = int(match.group("subject"))
                name = match.group("name").strip()
                picture_ids = list(dict.fromkeys(
                    int(value)
                    for value in re.findall(r"(?i)<Picture\s+(\d+)>", line)
                ))
                speaker = next(iter(re.findall(r"(?i)\(S(\d+)\)", line)), None)
                speaker_id = f"S{speaker}" if speaker else f"S{subject_id}"
            # Subject existence is defined by the authoritative subject
            # definition, not by whether a visual reference is available.
            # Story-only subjects may have no picture and no previous video
            # origin while still being valid registry entries.
            if match is None:
                continue
            if subject_id in registry:
                raise ValueError(f"Duplicate subject ID: {subject_id}")
            if any(
                str(item.get("name", "")).casefold() == name.casefold()
                for item in registry.values()
            ):
                raise ValueError(f"Duplicate subject name: {name}")
            if any(item.get("speaker_id") == speaker_id for item in registry.values()):
                raise ValueError(f"Duplicate speaker ID: {speaker_id}")
            origin_match = re.search(
                r"(?i)\b(?:created|established)\s+in\s+generated\s+video\s+"
                r"segment\s+(\d+)",
                line,
            )
            gender = _infer_gender(line)
            stored_record = None
            if isinstance(stored_records, Mapping):
                candidates = [
                    stored_records.get(subject_id),
                    stored_records.get(str(subject_id)),
                    stored_records.get(name),
                ]
                candidates.extend(stored_records.values())
                for candidate in candidates:
                    if not isinstance(candidate, Mapping):
                        continue
                    if (
                        str(candidate.get("subject_id", "")) == str(subject_id)
                        or str(candidate.get("name", "")).casefold()
                        == name.casefold()
                    ):
                        stored_record = candidate
                        break
            stored_query = (
                stored_record.get("dino_query")
                if stored_record is not None
                else None
            )
            has_stored_query = (
                isinstance(stored_query, str)
                and bool(stored_query.strip())
                and not _contains_provenance_marker(stored_query)
            )
            record = registry.register(
                subject_id,
                name=name,
                definition=line,
                identity_backend="insightface",
                dino_query=stored_query if has_stored_query else None,
                query_resolver=(
                    None if has_stored_query else query_resolver
                ),
                gender=gender,
                picture_ids=picture_ids,
                picture_id=picture_ids[0] if picture_ids else None,
                speaker_id=speaker_id,
                **({"origin_segment": int(origin_match.group(1))} if origin_match else {}),
            )
            if has_stored_query and stored_record is not None:
                record["dino_query_explicit"] = bool(
                    stored_record.get("dino_query_explicit", False)
                )
        return registry

    def get_subject(self, subject_id: Any) -> Optional[dict[str, Any]]:
        """Retrieve a record by mapping key or its stable subject ID."""

        try:
            if subject_id in self:
                return self[subject_id]
        except TypeError:
            pass
        wanted = str(subject_id)
        for record in self.values():
            if str(record.get("subject_id")) == wanted:
                return record
        return None

    def get(self, subject_id: Any, default: Any = None) -> Any:
        """Dict-compatible lookup that also accepts a stable ID alias."""

        return self.get_subject(subject_id) or default

    def iter_subjects(self) -> Iterable[dict[str, Any]]:
        """Iterate over all registered subject records."""

        return iter(self.values())

    def keys_for_query(self, query: str) -> tuple[Any, ...]:
        wanted = str(query).strip()
        return tuple(
            key for key, record in self.items()
            if str(record.get("dino_query", "")).strip() == wanted
        )

    def group_by_query(self) -> dict[str, "SubjectRegistry"]:
        """Return shared-query registry views without copying subject records."""

        grouped: dict[str, SubjectRegistry] = {}
        for key, record in self.items():
            query = str(record.get("dino_query", "person")).strip() or "person"
            grouped_registry = grouped.setdefault(
                query,
                type(self)(query_rules=self.query_rules),
            )
            grouped_registry[key] = record
        return grouped

    def subset(self, keys: Iterable[Any]) -> "SubjectRegistry":
        """Return a view-like registry sharing the same record dictionaries."""

        result = type(self)(query_rules=self.query_rules)
        for key in keys:
            if key in self:
                result[key] = self[key]
        return result

    def current_state_path(
        self,
        subject_key: Any,
        output_directory: os.PathLike[str] | str | None = None,
    ) -> str:
        record = self.get_subject(subject_key)
        if record is None:
            raise KeyError(f"Unknown subject: {subject_key!r}")
        configured = record.get("current_state_reference")
        base = os.fspath(output_directory) if output_directory is not None else ""
        if configured:
            path = os.path.expanduser(os.path.expandvars(os.fspath(configured)))
            if not os.path.isabs(path):
                path = os.path.join(base, path)
            return os.path.abspath(path)
        label = record.get("name") or record.get("subject_id") or subject_key
        return os.path.abspath(os.path.join(base, f"{_safe_name(label)}_current.png"))

    def has_valid_current_state(
        self,
        subject_key: Any,
        output_directory: os.PathLike[str] | str | None = None,
    ) -> bool:
        path = self.current_state_path(subject_key, output_directory)
        try:
            with Image.open(path) as image:
                image.verify()
            return True
        except (FileNotFoundError, OSError, Image.DecompressionBombError):
            return False

    current_state_is_valid = has_valid_current_state

    def update_current_state(self, subject_key: Any, path: Any = None) -> bool:
        """Commit a current-state path only when it contains a valid image."""

        record = self.get_subject(subject_key)
        if record is None:
            raise KeyError(f"Unknown subject: {subject_key!r}")
        candidate = os.path.abspath(os.fspath(path or record.get("current_state_reference")))
        try:
            with Image.open(candidate) as image:
                image.verify()
        except (FileNotFoundError, OSError, Image.DecompressionBombError):
            return False
        record["current_state_reference"] = candidate
        return True


def parse_subject_registry(
    subject_definitions: Any,
    *,
    query_rules: Mapping[Any, Any] | None = None,
    query_resolver: Optional[Callable[[str], Any]] = None,
    stored_records: Mapping[Any, Mapping[str, Any]] | None = None,
) -> SubjectRegistry:
    """Canonical parser used by both minimax and continuity code."""

    return SubjectRegistry.from_definitions(
        subject_definitions,
        query_rules=query_rules,
        query_resolver=query_resolver,
        stored_records=stored_records,
    )


__all__ = ["SubjectRegistry", "parse_subject_registry"]
