import pytest

from unitforma.core.slugs import SlugError, validate_slug


@pytest.mark.parametrize("value", ["acme", "acme-homes", "Riverside2", "a1b"])
def test_valid_slugs(value):
    assert validate_slug(value) == value.lower()


@pytest.mark.parametrize(
    "value", ["ab", "-acme", "acme-", "ac--me", "12345", "app", "www", "Acme Homes", "x" * 70]
)
def test_invalid_slugs(value):
    with pytest.raises(SlugError):
        validate_slug(value)
