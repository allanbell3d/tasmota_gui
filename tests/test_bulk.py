import threading
import time

import httpx
import pytest

from tasmota.core.bulk import TasmotaBulkExecutor, split_backlog

from conftest import status0


def make_executor(network, ips, logs=None, **kwargs):
    defaults = dict(
        threads=4,
        out_dir=None,
        timeout=1,
        retries=1,
        backoff=0,
        send_backlog=False,
        commands=[],
        info_mode="lite",
    )
    defaults.update(kwargs)
    log_cb = (lambda line, tag: logs.append((tag, line))) if logs is not None else None
    executor = TasmotaBulkExecutor(ips, log_callback=log_cb, transport=network.transport, **defaults)
    executor.ota_restart_wait = 0
    executor.ota_verification_interval = 0
    return executor


# ---------------------------------------------------------------- discovery
def test_full_mode_collects_template(network):
    def handler(cmd, request):
        if cmd == "Status 0":
            return httpx.Response(200, json=status0())
        if cmd == "Status 5":
            return httpx.Response(200, json={"StatusCFG": {"Template": '{"NAME":"Sonoff Basic"}'}})
        return httpx.Response(200, json={})

    network.add_device("10.0.0.5", handler=handler)
    result = make_executor(network, ["10.0.0.5"], info_mode="full").run()
    device = result.results[0]
    assert device.Ok and device.TemplateName == "Sonoff Basic" and device.RSSI == "80"


def test_discovery_reports_reasons(network):
    network.add_device("10.0.0.5")
    network.add_device("10.0.0.6", handler=lambda cmd, req: httpx.Response(200, text="<html>router</html>"))
    network.add_device("10.0.0.7", handler=lambda cmd, req: httpx.Response(200, json={"StatusFWR": {"Version": "1.0"}}))
    result = make_executor(network, ["10.0.0.5", "10.0.0.6", "10.0.0.7", "10.0.0.8"]).run()
    by_ip = {r.IP: r for r in result.results}
    assert by_ip["10.0.0.5"].Ok and by_ip["10.0.0.5"].Name == "Kitchen"
    assert "not a Tasmota" in by_ip["10.0.0.6"].Error
    assert by_ip["10.0.0.7"].Error == "Not a Tasmota device"
    assert "timed out" in by_ip["10.0.0.8"].Error
    assert result.rows_written == 1


@pytest.mark.parametrize("version", ["15.0.1(release-sensors)", "15.0.1(release-lite)", "14.3.0(85cff52-ir)"])
def test_non_default_official_builds_are_detected(network, version):
    network.add_device("10.0.0.5", version=version)
    assert make_executor(network, ["10.0.0.5"]).run().results[0].Ok


TASMOTA_401 = {"WARNING": "Need user=<username>&password=<password>"}


def needs_password(password="s3cret"):
    def handler(cmd, request):
        if request.url.params.get("password") == password:
            return httpx.Response(200, json=status0())
        return httpx.Response(401, json=TASMOTA_401)

    return handler


def test_auth_failure_is_not_retried(network):
    network.add_device("10.0.0.5", handler=needs_password())
    result = make_executor(network, ["10.0.0.5"], retries=3).run()
    assert result.results[0].Error == "HTTP 401 (device needs a web password)"
    assert len(network.log) == 1  # 401 is not retried

    network.log.clear()
    result = make_executor(network, ["10.0.0.5"], retries=3, web_password="wrong").run()
    assert result.results[0].Error == "HTTP 401 (wrong web password)"
    assert len(network.log) == 2  # one plain request, one with the password


def test_password_only_sent_to_devices_that_ask_for_it(network):
    network.add_device("10.0.0.5", handler=needs_password())
    network.add_device("10.0.0.6")  # open Tasmota device
    network.add_device("10.0.0.7", handler=lambda cmd, req: httpx.Response(401, text="router login"))
    result = make_executor(network, ["10.0.0.5", "10.0.0.6", "10.0.0.7", "10.0.0.8"], web_password="s3cret").run()
    by_ip = {r.IP: r for r in result.results}
    assert by_ip["10.0.0.5"].Ok and by_ip["10.0.0.6"].Ok
    assert by_ip["10.0.0.7"].Error == "HTTP 401 (not a Tasmota device?)"
    sent_password = {host for host, _, params in network.log if "password" in params}
    assert sent_password == {"10.0.0.5"}
    assert [p.get("user") for h, _, p in network.log if h == "10.0.0.5"] == [None, "admin"]


def test_password_redacted_from_exception_text(network):
    def leaky(cmd, request):
        if "password" in request.url.params:
            raise httpx.ReadError(f"boom while reading {request.url}")
        return httpx.Response(401, json=TASMOTA_401)

    network.add_device("10.0.0.5", handler=leaky)
    logs = []
    result = make_executor(network, ["10.0.0.5"], logs, web_password="s3cret!").run()
    assert "boom" in result.results[0].Error
    everything = result.results[0].Error + " ".join(line for _, line in logs)
    assert "s3cret" not in everything


def test_status_retried_after_server_error(network):
    replies = iter([httpx.Response(500), httpx.Response(200, json=status0())])
    network.add_device("10.0.0.5", handler=lambda cmd, req: next(replies))
    assert make_executor(network, ["10.0.0.5"], retries=2).run().results[0].Ok


def test_commands_not_retried_after_read_timeout(network):
    def handler(cmd, request):
        if cmd == "Status 0":
            return httpx.Response(200, json=status0())
        raise httpx.ReadTimeout("timed out", request=request)

    network.add_device("10.0.0.5", handler=handler)
    result = make_executor(
        network, ["10.0.0.5"], retries=3, send_backlog=True, commands=["Power on"], selected_ips=["10.0.0.5"]
    ).run()
    assert network.commands_for("10.0.0.5").count("Backlog Power on") == 1
    assert result.results[0].Action == "commands failed (see log)"


def test_command_encoding_matches_tasmota_expectation(network):
    network.add_device("10.0.0.5")
    make_executor(network, ["10.0.0.5"]).run()
    # Spaces must arrive as a single cmnd parameter value.
    assert network.log[0][1] == "Status 0"


# ---------------------------------------------------------------- commands
def test_split_backlog_chunks_by_count_and_length():
    commands = [f"SetOption{i} 1" for i in range(70)]
    chunks = split_backlog(commands)
    assert len(chunks) == 3
    assert all(chunk.startswith("Backlog ") for chunk in chunks)
    assert [len(c[len("Backlog "):].split("; ")) for c in chunks] == [30, 30, 10]
    flat = [cmd for c in chunks for cmd in c[len("Backlog "):].split("; ")]
    assert flat == commands  # order preserved

    long_cmds = ["Rule1 " + "x" * 400, "Rule2 " + "y" * 400, "Rule3 " + "z" * 400]
    chunks = split_backlog(long_cmds, max_length=1000)
    assert all(len(c) <= 1000 for c in chunks) and len(chunks) == 2


def test_split_backlog_refuses_semicolons_and_oversized():
    assert split_backlog(["Power on", "Rule1 on x do backlog a; b endon"]) is None
    assert split_backlog(["Rule1 " + "x" * 2000]) is None
    assert split_backlog(["Power on", "Reset 99"]) is None  # Tasmota drops Reset in Backlog
    # Length is counted in UTF-8 bytes, as Tasmota does.
    assert split_backlog(["DeviceName " + "\u00fc" * 600]) is None


def test_multi_chunk_backlog_waits_between_chunks(network):
    network.add_device("10.0.0.5")
    commands = [f"SetOption{i} 1" for i in range(35)]
    executor = make_executor(
        network, ["10.0.0.5"], send_backlog=True, commands=commands, selected_ips=["10.0.0.5"]
    )
    executor.backlog_seconds_per_command = 0.01
    executor.backlog_chunk_margin = 0.0
    started = time.monotonic()
    result = executor.run()
    sent = network.commands_for("10.0.0.5")[1:]
    assert len(sent) == 2 and sent[0].count("; ") == 29 and sent[1].count("; ") == 4
    assert time.monotonic() - started >= 0.3  # 30 queued commands x 0.01 s
    assert result.results[0].Action == "commands accepted"


def test_commands_sent_individually_in_order_when_semicolons(network):
    network.add_device("10.0.0.5")
    cmds = ["rule1 \"\"", "Rule1 on a do backlog b; c endon", "rule1 1"]
    make_executor(
        network, ["10.0.0.5"], send_backlog=True, commands=cmds, selected_ips=["10.0.0.5"]
    ).run()
    assert network.commands_for("10.0.0.5")[1:] == cmds


def test_command_unknown_reported_in_action(network):
    def handler(cmd, request):
        if cmd.startswith("Backlog"):
            return httpx.Response(200, json={"Command": "Unknown"})
        return httpx.Response(200, json=status0())

    network.add_device("10.0.0.5", handler=handler)
    result = make_executor(
        network, ["10.0.0.5"], send_backlog=True, commands=["Bogus 1"], selected_ips=["10.0.0.5"]
    ).run()
    assert result.results[0].Action == "commands failed (see log)"


def test_command_warning_is_reported_as_failure(network):
    def handler(cmd, request):
        if cmd.startswith("Backlog"):
            return httpx.Response(200, json={"WARNING": "Enter command cmnd="})
        return httpx.Response(200, json=status0())

    network.add_device("10.0.0.5", handler=handler)
    logs = []
    make_executor(
        network, ["10.0.0.5"], logs, send_backlog=True, commands=["Power on"], selected_ips=["10.0.0.5"]
    ).run()
    assert any(tag == "ERROR" and "Command failed" in line for tag, line in logs)


def test_empty_cmd_ips_means_no_devices(network):
    network.add_device("10.0.0.5")
    make_executor(
        network, ["10.0.0.5"], send_backlog=True, commands=["Power on"], selected_ips=["10.0.0.5"], cmd_ips=[]
    ).run()
    assert network.commands_for("10.0.0.5") == ["Status 0"]
    network.log.clear()
    make_executor(
        network, ["10.0.0.5"], send_backlog=True, commands=["Power on"], selected_ips=["10.0.0.5"], cmd_ips=None
    ).run()
    assert network.commands_for("10.0.0.5") == ["Status 0", "Backlog Power on"]


# ---------------------------------------------------------------- OTA
class OtaDevice:
    """Device that reports a new version once it has been restarted."""

    def __init__(
        self,
        hardware,
        old="14.0.0(release-tasmota32)",
        new="15.0.1(release-tasmota32)",
        reject_upgrade=False,
        via_minimal=False,
        keep_ota_url=False,
        current_ota_url=None,
        upgrade_times_out=False,
        stuck_minimal=False,
    ):
        self.hardware = hardware
        self.version = old
        self.new = new
        self.reject_upgrade = reject_upgrade
        self.via_minimal = via_minimal
        self.keep_ota_url = keep_ota_url
        self.current_ota_url = current_ota_url
        self.upgrade_times_out = upgrade_times_out
        self.stuck_minimal = stuck_minimal
        self.upgraded = False
        self.polls = 0

    def __call__(self, cmd, request):
        lower = cmd.lower()
        if lower == "status 0":
            if self.via_minimal and self.version == "15.0.1(release-minimal)":
                self.polls += 1
                if self.polls > 1 and not self.stuck_minimal:
                    self.version = self.new
            return httpx.Response(200, json=status0(hardware=self.hardware, version=self.version))
        if lower.startswith("otaurl") and self.keep_ota_url:
            return httpx.Response(200, json={"OtaUrl": "http://ota.tasmota.com/tasmota/release-14.0.0/tasmota.bin.gz"})
        if lower == "otaurl" and self.current_ota_url is not None:
            return httpx.Response(200, json={"OtaUrl": self.current_ota_url})
        if lower == "upgrade 1" and self.upgrade_times_out:
            self.upgraded = True
            raise httpx.ReadTimeout("timed out", request=request)
        if lower == "upgrade 1":
            if self.reject_upgrade:
                return httpx.Response(401, json={"WARNING": "Need user=<username>&password=<password>"})
            self.upgraded = True
            return httpx.Response(200, json={"Upgrade": f"Version {self.new} from ..."})
        if lower == "restart 1":
            if self.upgraded:
                self.version = "15.0.1(release-minimal)" if self.via_minimal else self.new
            return httpx.Response(200, json={"Restart": "Restarting"})
        return httpx.Response(200, json={cmd.split(" ")[0]: cmd.partition(" ")[2]})


def run_ota(network, device, logs, **kwargs):
    network.add_device("10.0.0.9", handler=device)
    return make_executor(
        network, ["10.0.0.9"], logs, do_upgrade=True, selected_ips=["10.0.0.9"], **kwargs
    ).run()


def test_ota_uses_variant_image_and_restores_variant_default(network):
    logs = []
    pinned = {"ESP32": "http://ota.tasmota.com/tasmota32/release-15.0.1/tasmota32.bin"}
    run_ota(network, OtaDevice("ESP32-C3 v0.4"), logs, ota_urls=pinned)
    cmds = network.commands_for("10.0.0.9")
    assert "OtaUrl http://ota.tasmota.com/tasmota32/release-15.0.1/tasmota32c3.bin" in cmds
    assert cmds[-1] == "OtaUrl http://ota.tasmota.com/tasmota32/release/tasmota32c3.bin"
    assert any("Firmware updated: 14.0.0" in line for _, line in logs)


def test_ota_result_reports_new_version(network):
    result = run_ota(network, OtaDevice("ESP8266EX", old="14.0.0(release-tasmota)", new="15.0.1(release-tasmota)"), [])
    device = result.results[0]
    assert device.Version == "15.0.1(release-tasmota)"
    assert device.Action == "OTA 14.0.0(release-tasmota) -> 15.0.1(release-tasmota)"


def test_ota_warns_when_version_unchanged(network):
    logs = []
    result = run_ota(network, OtaDevice("ESP8266EX", old="14.0.0(release-tasmota)", new="14.0.0(release-tasmota)"), logs)
    assert any(tag == "WARN" and "firmware unchanged" in line for tag, line in logs)
    assert result.results[0].Action.startswith("OTA: firmware unchanged")


def test_ota_waits_through_minimal_image(network):
    logs = []
    device = OtaDevice("ESP8266EX", old="14.0.0(release-tasmota)", new="15.0.1(release-tasmota)", via_minimal=True)
    result = run_ota(network, device, logs)
    assert any("minimal image" in line for _, line in logs)
    assert result.results[0].Version == "15.0.1(release-tasmota)"
    # OtaUrl is only restored once the final firmware is running.
    cmds = network.commands_for("10.0.0.9")
    assert cmds[-1].startswith("OtaUrl") and cmds[-2] == "Status 0"


def test_ota_aborts_when_device_keeps_old_ota_url(network):
    logs = []
    result = run_ota(network, OtaDevice("ESP8266EX", old="14.0.0(release-tasmota)", keep_ota_url=True), logs)
    assert "Upgrade 1" not in network.commands_for("10.0.0.9")
    assert result.results[0].Action.startswith("OTA aborted: OtaUrl not accepted")


def test_ota_rejected_upgrade_restores_default_url(network):
    logs = []
    pinned = {"ESP8266": "http://ota.tasmota.com/tasmota/release-15.0.0/tasmota.bin.gz"}
    run_ota(network, OtaDevice("ESP8266EX", old="14.0.0(release-tasmota)", reject_upgrade=True), logs, ota_urls=pinned)
    cmds = network.commands_for("10.0.0.9")
    assert "Restart 1" not in cmds
    assert cmds[-1] == "OtaUrl http://ota.tasmota.com/tasmota/release/tasmota.bin.gz"
    assert any(tag == "ERROR" and "Upgrade 1 not accepted" in line for tag, line in logs)


def test_ota_refuses_specialty_build(network):
    logs = []
    result = run_ota(network, OtaDevice("ESP8266EX", old="15.0.1(release-sensors)"), logs)
    assert not any(c.startswith("OtaUrl") for c in network.commands_for("10.0.0.9"))
    assert "sensors" in result.results[0].Action


def test_ota_refuses_unsupported_chip(network):
    logs = []
    run_ota(network, OtaDevice("ESP32-H2 v0.1"), logs)
    assert not any(cmd.startswith("OtaUrl") for cmd in network.commands_for("10.0.0.9"))
    assert any(tag == "ERROR" and "OTA skipped" in line for tag, line in logs)


def test_commands_after_upgrade_only_for_cmd_ips(network):
    logs = []
    run_ota(network, OtaDevice("ESP8266EX"), logs, send_backlog=True, commands=["Power on"], cmd_ips=[])
    assert "Backlog Power on" not in network.commands_for("10.0.0.9")


# ---------------------------------------------------------------- cancel
def test_cancel_interrupts_retry_backoff(network):
    executor = make_executor(network, ["10.0.0.99"], retries=5, backoff=10)
    timer = threading.Timer(0.2, executor.cancel)
    timer.start()
    started = time.monotonic()
    result = executor.run()
    timer.cancel()
    assert result.results == [] or not result.results[0].Ok
    assert time.monotonic() - started < 3
    assert executor.was_cancelled


def test_export_writes_files(network, tmp_path):
    pytest.importorskip("pandas")
    pytest.importorskip("openpyxl")
    network.add_device("10.0.0.5")
    result = make_executor(network, ["10.0.0.5"], out_dir=str(tmp_path)).run()
    assert result.rows_written == 1
    assert (tmp_path / result.xlsx_path.split("/")[-1]).exists()
    assert (tmp_path / result.csv_path.split("/")[-1]).exists()


def test_localized_auth_warning_gets_password(network):
    def german(cmd, request):
        if request.url.params.get("password") == "pw":
            return httpx.Response(200, json=status0())
        return httpx.Response(401, json={"WARNING": "Benötige user=<Benutzername>&password=<Passwort>"})

    network.add_device("10.0.0.5", handler=german)
    assert make_executor(network, ["10.0.0.5"], web_password="pw").run().results[0].Ok


def test_old_firmware_200_auth_warning_gets_password(network):
    def old(cmd, request):
        if request.url.params.get("password") == "pw":
            return httpx.Response(200, json=status0())
        return httpx.Response(200, json={"WARNING": "Need user=<username>&password=<password>"})

    network.add_device("10.0.0.5", handler=old)
    assert make_executor(network, ["10.0.0.5"], web_password="pw").run().results[0].Ok


def test_upgrade_timeout_continues_without_touching_ota_url(network):
    logs = []
    pinned = {"ESP8266": "http://ota.tasmota.com/tasmota/release-15.0.0/tasmota.bin.gz"}
    device = OtaDevice("ESP8266EX", old="14.0.0(release-tasmota)", new="15.0.1(release-tasmota)", upgrade_times_out=True)
    result = run_ota(network, device, logs, ota_urls=pinned)
    cmds = network.commands_for("10.0.0.9")
    upgrade_at = cmds.index("Upgrade 1")
    # No OtaUrl change right after the unanswered Upgrade 1; verified first.
    assert cmds[upgrade_at + 1] == "Restart 1"
    assert result.results[0].Action.startswith("OTA 14.0.0")
    assert cmds[-1] == "OtaUrl http://ota.tasmota.com/tasmota/release/tasmota.bin.gz"


def test_non_stock_current_ota_url_is_refused(network):
    logs = []
    device = OtaDevice(
        "ESP32-D0WD-V3", current_ota_url="http://ota.tasmota.com/tasmota32/release/tasmota32-DE.bin"
    )
    result = run_ota(network, device, logs)
    assert "Upgrade 1" not in network.commands_for("10.0.0.9")
    assert "language" in result.results[0].Action


def test_device_stuck_on_minimal_is_reported(network):
    executor_logs = []
    device = OtaDevice("ESP8266EX", old="14.0.0(release-tasmota)", via_minimal=True, stuck_minimal=True)
    network.add_device("10.0.0.9", handler=device)
    executor = make_executor(network, ["10.0.0.9"], executor_logs, do_upgrade=True, selected_ips=["10.0.0.9"])
    executor.ota_verification_retries = 2
    result = executor.run()
    assert result.results[0].Action == "OTA failed: device stuck on the minimal image"


def test_password_commands_masked_in_logs(network):
    network.add_device("10.0.0.5")
    logs = []
    make_executor(
        network,
        ["10.0.0.5"],
        logs,
        send_backlog=True,
        commands=["MqttPassword hunter2", "Rule1 a; b"],
        selected_ips=["10.0.0.5"],
    ).run()
    assert "MqttPassword hunter2" in network.commands_for("10.0.0.5")
    assert not any("hunter2" in line for _, line in logs)


def test_pause_after_user_backlog_line(network):
    network.add_device("10.0.0.5")
    executor = make_executor(
        network,
        ["10.0.0.5"],
        send_backlog=True,
        commands=["Backlog Power on; Delay 10; Power off", "Rule1 x; y"],
        selected_ips=["10.0.0.5"],
    )
    executor.backlog_seconds_per_command = 0.1
    executor.backlog_chunk_margin = 0.0
    started = time.monotonic()
    executor.run()
    assert time.monotonic() - started >= 0.3  # 3 queued entries x 0.1 s
