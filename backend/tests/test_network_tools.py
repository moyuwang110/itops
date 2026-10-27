"""运维工具箱：地址扫描与 DHCP 解析测试。"""
from __future__ import annotations

import pytest

from app.services import network_tool_service
from app.services.network_tool_service import (
    _is_private_cidr,
    _parse_dnsmasq_leases,
    _parse_isc_leases,
)


# ---------- CIDR 校验 ----------

def test_private_cidr_192_168():
    net = _is_private_cidr("192.168.1.0/24")
    assert net.num_addresses == 256


def test_private_cidr_10():
    net = _is_private_cidr("10.0.0.0/24")
    assert net.num_addresses == 256


def test_private_cidr_172_16():
    net = _is_private_cidr("172.16.5.0/24")
    assert net.num_addresses == 256


def test_public_cidr_rejected():
    with pytest.raises(ValueError, match="私有"):
        _is_private_cidr("8.8.8.0/24")


def test_ipv6_rejected():
    with pytest.raises(ValueError, match="IPv4"):
        _is_private_cidr("fd00::/64")


def test_too_large_cidr_rejected():
    with pytest.raises(ValueError, match="最多支持 256"):
        _is_private_cidr("10.0.0.0/16")


def test_invalid_cidr_rejected():
    with pytest.raises(ValueError, match="无效的 CIDR"):
        _is_private_cidr("not-a-cidr")


# ---------- ISC dhcpd 租约解析 ----------

def test_parse_isc_leases():
    content = """
lease 192.168.1.100 {
  starts 1 2026/09/30 08:00:00;
  ends 1 2026/09/30 20:00:00;
  hardware ethernet aa:bb:cc:dd:ee:ff;
  client-hostname "desktop-01";
}
lease 192.168.1.101 {
  starts 1 2026/09/30 09:00:00;
  ends 1 2026/09/30 21:00:00;
  hardware ethernet 11:22:33:44:55:66;
}
"""
    leases = _parse_isc_leases(content)
    assert len(leases) == 2
    assert leases[0]["ip"] == "192.168.1.100"
    assert leases[0]["mac"] == "aa:bb:cc:dd:ee:ff"
    assert leases[0]["hostname"] == "desktop-01"
    assert leases[0]["starts"] == "1 2026/09/30 08:00:00"
    assert leases[0]["ends"] == "1 2026/09/30 20:00:00"
    assert leases[1]["ip"] == "192.168.1.101"
    assert leases[1]["hostname"] == ""


# ---------- dnsmasq 租约解析 ----------

def test_parse_dnsmasq_leases():
    content = (
        "1790760000 aa:bb:cc:dd:ee:ff 192.168.1.100 desktop-01 01:aa:bb:cc:dd:ee:ff\n"
        "1790760100 11:22:33:44:55:66 192.168.1.101 * 01:11:22:33:44:55:66\n"
    )
    leases = _parse_dnsmasq_leases(content)
    assert len(leases) == 2
    assert leases[0]["ip"] == "192.168.1.100"
    assert leases[0]["mac"] == "aa:bb:cc:dd:ee:ff"
    assert leases[0]["hostname"] == "desktop-01"
    assert leases[1]["hostname"] == ""


def test_parse_dnsmasq_empty():
    assert _parse_dnsmasq_leases("") == []
    assert _parse_dnsmasq_leases("# comment\n") == []
