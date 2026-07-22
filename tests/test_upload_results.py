from websync.pipeline.upload_results import (
    collect_mark_entries,
    upload_all_ok,
    upload_any_ok,
)


def test_upload_all_ok_requires_full_pending_set():
    pending = ["10.0.0.1", "10.0.0.2"]
    assert upload_all_ok({"10.0.0.1": True, "10.0.0.2": True}, pending)
    assert not upload_all_ok({"10.0.0.1": True}, pending)
    assert not upload_all_ok({"10.0.0.1": True, "10.0.0.2": False}, pending)
    assert not upload_any_ok({})
    assert upload_any_ok({"10.0.0.1": False, "10.0.0.2": True})


def test_collect_mark_entries_skips_already_synced():
    arts = [
        {"url": "https://a/1", "title": "A"},
        {"url": "https://a/2", "title": "B"},
    ]
    synced = {("https://a/1", "10.0.0.1")}

    def is_synced(url, ip):
        return (url, ip) in synced

    batch = collect_mark_entries(
        {"10.0.0.1": True, "10.0.0.2": False},
        arts,
        site_name="Site",
        is_synced_for_device=is_synced,
    )
    urls = {(e["url"], e["device_ip"]) for e in batch}
    assert ("https://a/1", "10.0.0.1") not in urls
    assert ("https://a/2", "10.0.0.1") in urls
    assert all(e["device_ip"] == "10.0.0.1" for e in batch)


def test_mask_secret_utility():
    from websync.config.secrets import mask_secret, redact_config_for_log

    assert mask_secret("abcdefghij") == "******ghij"
    red = redact_config_for_log(
        {"ai_summary": {"api_key": "sk-secret-key-1234"}, "x3_ip": "1.2.3.4"}
    )
    assert red["ai_summary"]["api_key"] != "sk-secret-key-1234"
    assert red["x3_ip"] == "1.2.3.4"
