from __future__ import annotations

from time import perf_counter

import pytest

from app.services.secret_redaction import REDACTED, redact_secret_text


def _redact_and_assert_idempotent(value: str) -> str:
    redacted = redact_secret_text(value)

    assert redact_secret_text(redacted) == redacted
    return redacted


@pytest.mark.parametrize(
    ("value", "secret"),
    [
        ("Authorization: Bearer eyJhbGciOiJIUzI1Ni.secret.signature", "eyJhbGci"),
        ("bearer opaque-token_1234567890", "opaque-token"),
        ("token=gAAAAABmQ0x1234567890abcdefghijklmnopqrstuvwxyzABCDE", "gAAAAA"),
        ("git token ghp_1234567890abcdefghijklmnopqrstuvwxyz", "ghp_123456"),
        ("github_pat_11AA0_abcdefghijklmnopqrstuvwxyz0123456789", "github_pat_"),
        ("remote failed for glpat-abcdefghijklmnopqrst", "glpat-"),
    ],
)
def test_redacts_bearer_fernet_and_git_tokens(value: str, secret: str) -> None:
    redacted = _redact_and_assert_idempotent(value)

    assert secret not in redacted
    assert REDACTED in redacted


@pytest.mark.parametrize(
    "value",
    [
        "postgresql+asyncpg://conductor:p%40ssword@postgres:5432/airflow",
        "postgres://user:plain-password@db.internal/project?sslmode=require",
        "mysql://root:hunter2@mysql/project",
        "redis://:redis-secret@redis:6379/0",
        "https://oauth2:ghp_1234567890abcdefghijklmnopqrstuvwxyz@github.com/org/repo.git",
    ],
)
def test_redacts_credentials_embedded_in_urls(value: str) -> None:
    redacted = _redact_and_assert_idempotent(f"command failed: {value}")

    assert value not in redacted
    assert REDACTED in redacted
    for secret in ("p%40ssword", "plain-password", "hunter2", "redis-secret", "ghp_"):
        assert secret not in redacted


def test_redacts_query_string_credentials_without_destroying_safe_context() -> None:
    value = (
        "GET https://service.example/api?project=analytics&password=query-secret"
        "&access_token=query-token&api_key=query-api-key&safe=value"
    )

    redacted = _redact_and_assert_idempotent(value)

    assert "project=analytics" in redacted
    assert "safe=value" in redacted
    assert "query-secret" not in redacted
    assert "query-token" not in redacted
    assert "query-api-key" not in redacted
    assert redacted.count(REDACTED) == 3


@pytest.mark.parametrize("label", ["PRIVATE KEY", "RSA PRIVATE KEY", "EC PRIVATE KEY", "OPENSSH PRIVATE KEY"])
def test_redacts_complete_private_key_blocks(label: str) -> None:
    value = (
        f"before\n-----BEGIN {label}-----\n"
        "c3VwZXItc2VjcmV0LWtleS1tYXRlcmlhbA==\n"
        f"-----END {label}-----\nafter"
    )

    redacted = _redact_and_assert_idempotent(value)

    assert "c3VwZXIt" not in redacted
    assert "BEGIN" not in redacted
    assert "END" not in redacted
    assert redacted == f"before\n{REDACTED}\nafter"


@pytest.mark.parametrize(
    "value",
    [
        "before\n-----BEGIN PRIVATE KEY-----\nunclosed-secret-material",
        (
            "before\n-----BEGIN RSA PRIVATE KEY-----\nsecret-material\n"
            "-----END EC PRIVATE KEY-----\nafter"
        ),
    ],
)
def test_redacts_unmatched_private_key_begin_through_remaining_text(value: str) -> None:
    redacted = _redact_and_assert_idempotent(value)

    assert redacted == f"before\n{REDACTED}"
    assert "secret-material" not in redacted
    assert "BEGIN" not in redacted


def test_repeated_unmatched_private_key_headers_are_processed_promptly() -> None:
    value = "before\n" + "-----BEGIN PRIVATE KEY-----\n" * 3_200

    started = perf_counter()
    redacted = redact_secret_text(value)
    elapsed = perf_counter() - started

    assert redacted == f"before\n{REDACTED}"
    assert elapsed < 0.5


def test_redacts_rendered_env_and_structured_secret_values() -> None:
    value = "\n".join(
        [
            "SAFE_MODE=enabled",
            "AIRFLOW_ADMIN_PASSWORD=admin-password",
            "export GIT_TOKEN='github_pat_11AA0_secretvalue'",
            'FERNET_KEY="gAAAAABmQ0x_secretvalue"',
            "DATABASE_URL=postgresql://user:database-password@db/project",
            'payload={"client_secret":"json-secret","password": "json-password"}',
            "api_key: yaml-secret",
        ]
    )

    redacted = _redact_and_assert_idempotent(value)

    assert "SAFE_MODE=enabled" in redacted
    for secret in (
        "admin-password",
        "github_pat_",
        "gAAAAA",
        "database-password",
        "json-secret",
        "json-password",
        "yaml-secret",
    ):
        assert secret not in redacted
    assert redacted.count(REDACTED) >= 7


LEADING_SECRET_MARKER_KEYS = [
    "PRIVATE_KEY",
    "PRIVATE_KEY_B64",
    "SECRET_VALUE",
    "SECRET_ACCESS_KEY",
    "PASSWORD_HASH",
    "TOKEN_VALUE",
    "API_KEY_VALUE",
    "FERNET_KEY_VALUE",
    "DATABASE_URL_VALUE",
]


@pytest.mark.parametrize("key", LEADING_SECRET_MARKER_KEYS)
@pytest.mark.parametrize(
    ("template", "expected_template"),
    [
        ("{key}=sensitive-value", "{key}=[REDACTED]"),
        ("{key}: sensitive value # safe-comment", "{key}: [REDACTED] # safe-comment"),
        ('{key}: "sensitive value" # safe-comment', '{key}: "[REDACTED]" # safe-comment'),
        ("{key}: 'sensitive value' # safe-comment", "{key}: '[REDACTED]' # safe-comment"),
        ('"{key}": sensitive value # safe-comment', '"{key}": [REDACTED] # safe-comment'),
        ('{{"{key}":"sensitive value","safe":"kept"}}', '{{"{key}":"[REDACTED]","safe":"kept"}}'),
    ],
)
def test_redacts_leading_marker_env_names_in_assignments_and_mappings(
    key: str,
    template: str,
    expected_template: str,
) -> None:
    value = template.format(key=key)

    redacted = _redact_and_assert_idempotent(value)

    assert redacted == expected_template.format(key=key)
    assert "sensitive value" not in redacted


@pytest.mark.parametrize(
    "key",
    ["TEXT_TOKENIZER_NAME", "AUTH_PASSWORDLESS", "ENABLE_SECRETS_LOGGING"],
)
def test_does_not_redact_secret_marker_substring_near_misses(key: str) -> None:
    value = f'{key}=safe-value\n{key}: "safe mapping value"'

    assert redact_secret_text(value) == value


def test_repeated_secret_markers_without_delimiters_are_processed_promptly() -> None:
    value = "PASSWORD" * 1_600

    started = perf_counter()
    redacted = redact_secret_text(value)
    elapsed = perf_counter() - started

    assert redacted == value
    assert elapsed < 0.5


@pytest.mark.parametrize(
    ("value", "secret", "expected"),
    [
        (
            'before {"password":"alpha beta, !&:@ \\"quoted\\" punctuation","safe":"kept"} after',
            'alpha beta, !&:@ \\"quoted\\" punctuation',
            f'before {{"password":"{REDACTED}","safe":"kept"}} after',
        ),
        (
            "before\npassword: 'alpha beta, !&:@ ''quoted'' punctuation'\nafter",
            "alpha beta, !&:@ ''quoted'' punctuation",
            f"before\npassword: '{REDACTED}'\nafter",
        ),
        (
            "environment:\n  AWS_SECRET_ACCESS_KEY: alpha beta, !&:@\n  SAFE_MODE: enabled",
            "alpha beta, !&:@",
            f"environment:\n  AWS_SECRET_ACCESS_KEY: {REDACTED}\n  SAFE_MODE: enabled",
        ),
        (
            "before\n-----BEGIN ENCRYPTED PRIVATE KEY-----\n"
            "c3VwZXItc2VjcmV0LWtleS1tYXRlcmlhbA==\n"
            "-----END ENCRYPTED PRIVATE KEY-----\nafter",
            "c3VwZXItc2VjcmV0LWtleS1tYXRlcmlhbA==",
            f"before\n{REDACTED}\nafter",
        ),
        (
            "request https://user:alpha@beta@db.example/x?mode=safe failed",
            "user:alpha@beta",
            f"request https://{REDACTED}@db.example/x?mode=safe failed",
        ),
    ],
    ids=[
        "quoted-json-spaces-punctuation",
        "quoted-yaml-spaces-punctuation",
        "compose-env-secret-mapping",
        "encrypted-private-key",
        "url-userinfo-raw-at",
    ],
)
def test_redacts_review_regressions_without_destroying_safe_context(
    value: str,
    secret: str,
    expected: str,
) -> None:
    redacted = _redact_and_assert_idempotent(value)

    assert secret not in redacted
    assert redacted == expected


def test_malformed_private_key_prefix_does_not_hide_following_real_block() -> None:
    value = (
        "before\n"
        "-----BEGIN malformed without terminator\n"
        "-----BEGIN PRIVATE KEY-----\n"
        "secret-material\n"
        "-----END PRIVATE KEY-----\n"
        "after"
    )

    redacted = _redact_and_assert_idempotent(value)

    assert redacted == (
        "before\n"
        "-----BEGIN malformed without terminator\n"
        f"{REDACTED}\n"
        "after"
    )
    assert "secret-material" not in redacted


@pytest.mark.parametrize("quote", ['"', "'"])
def test_unmatched_multiline_yaml_quote_redacts_the_remainder(quote: str) -> None:
    value = f"before\nPASSWORD: {quote}alpha\nbeta\nSAFE_MODE: would-leak"

    redacted = _redact_and_assert_idempotent(value)

    assert redacted == f"before\nPASSWORD: {quote}{REDACTED}"
    assert "alpha" not in redacted
    assert "beta" not in redacted
    assert "would-leak" not in redacted


@pytest.mark.parametrize(
    ("key", "quoted_secret", "quote"),
    [
        ("PASSWORD", 'alpha\n    beta \\"inside\\"\n    gamma', '"'),
        ("TOKEN_BACKUP", "alpha\n    beta ''inside''\n    gamma", "'"),
    ],
)
def test_redacts_multiline_quoted_yaml_and_preserves_following_sibling(
    key: str,
    quoted_secret: str,
    quote: str,
) -> None:
    value = (
        f"environment:\n  {key}: {quote}{quoted_secret}{quote}\n"
        "  SAFE_MODE: kept\nafter: visible"
    )

    redacted = _redact_and_assert_idempotent(value)

    assert redacted == (
        f"environment:\n  {key}: {quote}{REDACTED}{quote}\n"
        "  SAFE_MODE: kept\nafter: visible"
    )
    assert "alpha" not in redacted
    assert "gamma" not in redacted


@pytest.mark.parametrize(
    ("key", "indicator"),
    [
        ("PASSWORD", "|"),
        ("PASSWORD_BACKUP", ">-"),
        ("TOKEN_ARCHIVE", "|2+"),
        ("SECRET_HISTORY", ">-2"),
    ],
)
def test_redacts_yaml_block_scalars_and_preserves_following_sibling(
    key: str,
    indicator: str,
) -> None:
    value = (
        "environment:\n"
        f"  {key}: {indicator} # scalar settings\n"
        "    alpha secret\n"
        "    beta secret\n"
        "\n"
        "  SAFE_MODE: kept\n"
        "after: visible"
    )

    redacted = _redact_and_assert_idempotent(value)

    assert redacted == (
        "environment:\n"
        f"  {key}: {REDACTED}\n"
        "  SAFE_MODE: kept\n"
        "after: visible"
    )
    assert "alpha secret" not in redacted
    assert "beta secret" not in redacted


@pytest.mark.parametrize(
    ("value", "expected", "safe_context"),
    [
        (
            "[{TOKEN_BACKUP: alpha beta}] after-safe",
            f"[{{TOKEN_BACKUP: {REDACTED}}}] after-safe",
            "after-safe",
        ),
        (
            "{PASSWORD: alpha beta} after-safe",
            f"{{PASSWORD: {REDACTED}}} after-safe",
            "after-safe",
        ),
        (
            "{PASSWORD: alpha beta # safe comment\n} after-safe",
            f"{{PASSWORD: {REDACTED} # safe comment\n}} after-safe",
            "safe comment",
        ),
    ],
)
def test_flow_yaml_redaction_stops_at_structural_or_comment_boundary(
    value: str,
    expected: str,
    safe_context: str,
) -> None:
    redacted = _redact_and_assert_idempotent(value)

    assert redacted == expected
    assert safe_context in redacted
    assert "alpha beta" not in redacted


@pytest.mark.parametrize("key", ["PASSWORD", "PASSWORD_BACKUP"])
def test_redacts_unquoted_flow_yaml_scalars_through_spaces(key: str) -> None:
    value = f"{{{key}: alpha beta, SAFE: kept}}"

    redacted = _redact_and_assert_idempotent(value)

    assert redacted == f"{{{key}: {REDACTED}, SAFE: kept}}"
    assert "alpha" not in redacted
    assert "beta" not in redacted


def test_redaction_is_idempotent_and_leaves_non_secret_text_unchanged() -> None:
    safe = "docker compose failed for project 012345 at step validate_compose"
    sensitive = "password=top-secret Authorization: Bearer " + "token-value-12345678"

    assert redact_secret_text(safe) == safe
    assert redact_secret_text(redact_secret_text(sensitive)) == redact_secret_text(sensitive)


@pytest.mark.parametrize(
    "value",
    [
        "{PASSWORD: [alpha, beta], SAFE: kept}",
        "{PASSWORD: {first: alpha, second: beta}, SAFE: kept}",
        '{PASSWORD: ["alpha, one", "beta, two"], SAFE: kept}',
    ],
)
def test_redacts_complete_nested_flow_yaml_secret_values(value: str) -> None:
    redacted = _redact_and_assert_idempotent(value)

    assert "alpha" not in redacted
    assert "beta" not in redacted
    assert "SAFE: kept" in redacted
    assert redacted == f"{{PASSWORD: {REDACTED}, SAFE: kept}}"


def test_yaml_single_quoted_backslash_does_not_consume_safe_sibling() -> None:
    value = r"{PASSWORD: 'alpha\', SAFE: 'kept'}"

    redacted = _redact_and_assert_idempotent(value)

    assert redacted == f"{{PASSWORD: '{REDACTED}', SAFE: 'kept'}}"


def test_malformed_same_line_begin_cannot_hide_recognized_private_key() -> None:
    marker = "-" * 5
    begin = f"{marker}BEGIN "
    value = (
        f"{begin}malformed {begin}EC PRIVATE KEY{marker}\n"
        f"secret-material\n{marker}END EC PRIVATE KEY{marker}"
    )

    redacted = _redact_and_assert_idempotent(value)

    assert "secret-material" not in redacted
    assert redacted.endswith(REDACTED)
