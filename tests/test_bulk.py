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


def test_auth_failure_is_not_retried_and_password_not_logged(network):
    def needs_auth(cmd, request):
        if request.url.params.get("password") == "s3cret":
            return httpx.Response(200, json=status0())
        return httpx.Response(401, json={"WARNING": "Need user=<username>&password=<password>"})

    network.add_device("10.0.0.5", handler=needs_auth)
    logs = []
    result = make_executor(network, ["10.0.0.5"], logs, retries=3).run()
    assert "HTTP 401" in result.results[0].Error
    assert len(network.log) == 1  # 401 is not retried

    network.log.clear()
    result = make_executor(network, ["10.0.0.5"], logs, web_password="s3cret").run()
    assert result.results[0].Ok
    assert network.log[0][2]["user"] == "admin"
    assert all("s3cret" not in line for _, line in logs)


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


def test_commands_sent_individually_in_order_when_semicolons(network):
    network.add_device("10.0.0.5")
    cmds = ["rule1 \"\"", "Rule1 on a do backlog b; c endon", "rule1 1"]
    make_executor(
        network, ["10.0.0.5"], send_backlog=True, commands=cmds, selected_ips=["10.0.0.5"]
    ).run()
    assert network.commands_for("10.0.0.5")[1:] == cmds


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

    def __init__(self, hardware, old="14.0.0(release-tasmota32)", new="15.0.1(release-tasmota32)", reject_upgrade=False):
        self.hardware = hardware
        self.version = old
        self.new = new
        self.reject_upgrade = reject_upgrade
        self.upgraded = False

    def __call__(self, cmd, request):
        lower = cmd.lower()
        if lower == "status 0":
            return httpx.Response(200, json=status0(hardware=self.hardware, version=self.version))
        if lower == "upgrade 1":
            if self.reject_upgrade:
                return httpx.Response(401, json={"WARNING": "Need user=<username>&password=<password>"})
            self.upgraded = True
            return httpx.Response(200, json={"Upgrade": f"Version {self.new} from ..."})
        if lower == "restart 1":
            if self.upgraded:
                self.version = self.new
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


def test_ota_warns_when_version_unchanged(network):
    logs = []
    run_ota(network, OtaDevice("ESP8266EX", new="14.0.0(release-tasmota32)"), logs)
    assert any(tag == "WARN" and "firmware unchanged" in line for tag, line in logs)


def test_ota_aborts_without_waiting_when_upgrade_rejected(network):
    logs = []
    network_device = OtaDevice("ESP8266EX", reject_upgrade=True)
    run_ota(network, network_device, logs)
    cmds = network.commands_for("10.0.0.9")
    assert "Restart 1" not in cmds
    assert any(tag == "ERROR" and "Upgrade 1 not accepted" in line for tag, line in logs)


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
