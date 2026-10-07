from selfheal.security.scrubber import scrub_secrets


def test_scrubs_api_key():
    text = 'api_key="super-secret-api-key-123456"'

    result = scrub_secrets(text)

    assert "super-secret-api-key-123456" not in result
    assert "[REDACTED]" in result


def test_scrubs_password():
    text = 'password="my-password-123456"'

    result = scrub_secrets(text)

    assert "my-password-123456" not in result
    assert "[REDACTED]" in result


def test_scrubs_bearer_token():
    text = "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456"

    result = scrub_secrets(text)

    assert "abcdefghijklmnopqrstuvwxyz123456" not in result
    assert "Bearer [REDACTED]" in result


def test_scrubs_github_token():
    text = "token=ghp_abcdefghijklmnopqrstuvwxyz1234567890"

    result = scrub_secrets(text)

    assert "ghp_abcdefghijklmnopqrstuvwxyz1234567890" not in result
    assert "[REDACTED_GITHUB_TOKEN]" in result


def test_scrubs_google_api_key():
    text = "AIzaSyA1234567890abcdefghijklmnop"

    result = scrub_secrets(text)

    assert "AIzaSyA1234567890abcdefghijklmnop" not in result
    assert "[REDACTED_GOOGLE_KEY]" in result


def test_scrubs_jwt():
    text = (
        "eyJabcdefghijklmnop.eyJqrstuvwxyz123456."
        "eyJabcdef123456"
    )

    result = scrub_secrets(text)

    assert "eyJabcdefghijklmnop" not in result
    assert "[REDACTED_JWT]" in result


def test_scrubs_private_key():
    text = """-----BEGIN PRIVATE KEY-----
secret-private-key-material
-----END PRIVATE KEY-----"""

    result = scrub_secrets(text)

    assert "secret-private-key-material" not in result
    assert "[REDACTED_PRIVATE_KEY]" in result


def test_preserves_normal_code():
    text = 'print("hello world")\nx = calculate_value(10)'

    result = scrub_secrets(text)

    assert result == text