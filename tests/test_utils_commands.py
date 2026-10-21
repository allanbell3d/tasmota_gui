from tasmota.core.commands import CommandRecord, extract_categories, load_command_library
from tasmota.core.utils import is_valid_ip, parse_ip_range, safe_extract_json, validate_ip_ranges


def test_validate_ip_ranges_docstring_example():
    valid, invalid = validate_ip_ranges("192.168.1.1\n192.168.1.10-20\nnot-an-ip\n10.0.0.1\n\n")
    assert len(valid) == 13
    assert invalid == ["not-an-ip"]


def test_parse_ip_range_rejects_bad_input():
    assert parse_ip_range("192.168.1.20-10") == (False, [])
    assert parse_ip_range("192.168.1.1-256") == (False, [])
    assert parse_ip_range("192.168.300.1-2") == (False, [])
    assert parse_ip_range("192.168.1.1-192.168.1.5") == (False, [])
    assert is_valid_ip(" 10.0.0.255 ")
    assert not is_valid_ip("10.0.0.256")


def test_safe_extract_json():
    assert safe_extract_json('{"a": 1}') == {"a": 1}
    assert safe_extract_json('junk {"a": 1} junk') == {"a": 1}
    assert safe_extract_json("<html><body>nope</body></html>") is None
    assert safe_extract_json("") is None


def test_bundled_command_library_loads():
    records = load_command_library()
    assert len(records) > 100
    assert all(record.name for record in records)
    categories, _ = extract_categories(records)
    assert categories == sorted(categories, key=str.lower)


def test_backlog_entry():
    record = CommandRecord(name="TelePeriod", value=" 30 ", description="", category="", metadata={})
    assert record.backlog_entry() == "TelePeriod 30"
