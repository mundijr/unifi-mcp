"""Post-write persistence verification for fetch-merge-put manager updates.

Regression coverage for the silent-no-op write: the controller can answer a
legacy /rest/wlanconf (or /rest/networkconf) PUT with rc:ok yet silently not
persist the requested fields. The managers used to return success
unconditionally; they now re-read and confirm the change actually landed.
"""

from unittest.mock import AsyncMock, MagicMock

from unifi_core.network.managers.network_manager import NetworkManager, _unpersisted_fields

WLAN_ID = "60c7d8e9f0a1b2c3d4e5f6a7"
NETWORK_ID = "70d8e9f0a1b2c3d4e5f6a7b8"


def _make_connection():
    """Connection mock whose cache always misses, so each fetch hits request()."""
    conn = MagicMock()
    conn.site = "default"
    conn.request = AsyncMock()
    conn.get_cached = MagicMock(return_value=None)
    conn._update_cache = MagicMock()
    conn._invalidate_cache = MagicMock()
    conn.ensure_connected = AsyncMock(return_value=True)
    return conn


def _wlan(**overrides):
    base = {"_id": WLAN_ID, "name": "IoT", "proxy_arp": False, "minrate_ng_data_rate_kbps": 1000}
    base.update(overrides)
    return base


def _network(**overrides):
    base = {"_id": NETWORK_ID, "name": "Default", "igmp_snooping": False}
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# _unpersisted_fields helper
# ---------------------------------------------------------------------------


def test_unpersisted_flags_field_that_did_not_move():
    before = {"proxy_arp": False}
    after = {"proxy_arp": False}  # unchanged after the write
    assert _unpersisted_fields(before, after, {"proxy_arp": True}) == ["proxy_arp"]


def test_unpersisted_accepts_field_that_changed():
    before = {"proxy_arp": False}
    after = {"proxy_arp": True}
    assert _unpersisted_fields(before, after, {"proxy_arp": True}) == []


def test_unpersisted_ignores_noop_request():
    # Requested value already equals current state -> nothing to verify.
    before = {"proxy_arp": True}
    after = {"proxy_arp": True}
    assert _unpersisted_fields(before, after, {"proxy_arp": True}) == []


def test_unpersisted_skips_write_only_fields():
    before = {"x_passphrase": "old"}
    after = {}  # controller never echoes the passphrase back
    assert _unpersisted_fields(before, after, {"x_passphrase": "new"}) == []


# ---------------------------------------------------------------------------
# update_wlan
# ---------------------------------------------------------------------------


async def test_update_wlan_fails_when_not_persisted():
    conn = _make_connection()
    mgr = NetworkManager(conn)
    before = _wlan()
    # get(pre) -> put(ignored) -> get(post == pre)
    conn.request.side_effect = [[before], {}, [_wlan()]]

    ok, err = await mgr.update_wlan(WLAN_ID, {"proxy_arp": True})

    assert ok is False
    assert err is not None and "proxy_arp" in err


async def test_update_wlan_succeeds_when_persisted():
    conn = _make_connection()
    mgr = NetworkManager(conn)
    conn.request.side_effect = [[_wlan()], {}, [_wlan(proxy_arp=True)]]

    ok, err = await mgr.update_wlan(WLAN_ID, {"proxy_arp": True})

    assert ok is True
    assert err is None


async def test_update_wlan_succeeds_for_write_only_field():
    conn = _make_connection()
    mgr = NetworkManager(conn)
    # passphrase never round-trips; must not be reported as unpersisted
    conn.request.side_effect = [[_wlan()], {}, [_wlan()]]

    ok, err = await mgr.update_wlan(WLAN_ID, {"x_passphrase": "newsecret"})

    assert ok is True
    assert err is None


# ---------------------------------------------------------------------------
# update_network (shares the same verification path)
# ---------------------------------------------------------------------------


async def test_update_network_fails_when_not_persisted():
    conn = _make_connection()
    mgr = NetworkManager(conn)
    conn.request.side_effect = [[_network()], {}, [_network()]]

    ok, err = await mgr.update_network(NETWORK_ID, {"igmp_snooping": True})

    assert ok is False
    assert err is not None and "igmp_snooping" in err
