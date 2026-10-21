import json

from tasmota.core.settings import ENV_SETTINGS_DIR, SETTINGS_FILENAME, SettingsStore, UserSettings


def test_round_trip_keeps_unknown_keys(tmp_path):
    store = SettingsStore(tmp_path)
    settings = UserSettings(ip_ranges="10.0.0.1-5", commands=["TelePeriod 30"], web_password="pw")
    settings.extra["_command_notes"] = {"TelePeriod 30": "note"}
    assert store.save(settings) is None
    loaded, warning = SettingsStore(tmp_path).load()
    assert warning is None
    assert loaded.ip_ranges == "10.0.0.1-5"
    assert loaded.commands == ["TelePeriod 30"]
    assert loaded.web_password == "pw"
    assert loaded.extra["_command_notes"] == {"TelePeriod 30": "note"}


def test_bad_types_fall_back_to_defaults(tmp_path):
    (tmp_path / SETTINGS_FILENAME).write_text(
        json.dumps({"threads": "abc", "timeout": -1, "retries": True, "info_mode": "huge", "commands": [1, "Power on"]})
    )
    loaded, warning = SettingsStore(tmp_path).load()
    defaults = UserSettings()
    assert warning is None
    assert (loaded.threads, loaded.timeout, loaded.retries, loaded.info_mode) == (
        defaults.threads,
        defaults.timeout,
        defaults.retries,
        defaults.info_mode,
    )
    assert loaded.commands == ["Power on"]


def test_corrupt_file_is_preserved_not_overwritten(tmp_path):
    path = tmp_path / SETTINGS_FILENAME
    path.write_text("{not json")
    loaded, warning = SettingsStore(tmp_path).load()
    assert warning and "Using defaults" in warning
    backups = list(tmp_path.glob(SETTINGS_FILENAME + ".corrupt-*"))
    assert len(backups) == 1 and backups[0].read_text() == "{not json"
    assert loaded == UserSettings()


def test_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_SETTINGS_DIR, str(tmp_path / "env"))
    store = SettingsStore(tmp_path / "ignored")
    assert store.save(UserSettings(ip_ranges="1.2.3.4")) is None
    assert (tmp_path / "env" / SETTINGS_FILENAME).is_file()
    assert not (tmp_path / "ignored").exists()


def test_save_falls_back_when_first_dir_unwritable(tmp_path):
    blocker = tmp_path / "file_not_dir"
    blocker.write_text("x")
    store = SettingsStore()
    store._dirs = [blocker / "sub", tmp_path / "fallback"]
    assert store.save(UserSettings(ip_ranges="1.2.3.4")) is None
    assert (tmp_path / "fallback" / SETTINGS_FILENAME).is_file()


def test_frozen_exe_reads_bundled_seed_and_saves_next_to_exe(tmp_path, monkeypatch):
    import sys

    from tasmota.core import settings as settings_mod

    exe_dir = tmp_path / "app"
    bundle = tmp_path / "_MEI123"
    (bundle / ".private").mkdir(parents=True)
    (bundle / ".private" / SETTINGS_FILENAME).write_text(json.dumps({"ip_ranges": "10.9.9.1-9"}))
    exe_dir.mkdir()
    monkeypatch.delenv(ENV_SETTINGS_DIR, raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "TasmotaBulkGUI.exe"))
    monkeypatch.setattr(settings_mod, "_fallback_dir", lambda: tmp_path / "appdata")

    store = SettingsStore()
    loaded, warning = store.load()
    assert warning is None and loaded.ip_ranges == "10.9.9.1-9"
    assert store.save(loaded) is None
    assert (exe_dir / ".private" / SETTINGS_FILENAME).is_file()
    # After the first save the file next to the exe wins over the seed.
    (exe_dir / ".private" / SETTINGS_FILENAME).write_text(json.dumps({"ip_ranges": "1.1.1.1"}))
    assert SettingsStore().load()[0].ip_ranges == "1.1.1.1"
