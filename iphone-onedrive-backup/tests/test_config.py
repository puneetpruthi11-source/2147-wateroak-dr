from iphone_backup.config import load_config, save_config


def test_defaults_fill_in_paths(tmp_path):
    cfg = load_config(tmp_path)
    assert cfg.state_dir == str(tmp_path)
    assert cfg.mount_point.endswith("/mnt")
    assert cfg.tenant == "consumers"
    assert cfg.chunk_size_bytes == 10 * 1024 * 1024


def test_save_and_reload_roundtrip(tmp_path):
    cfg = load_config(tmp_path)
    cfg.client_id = "abc-123"
    cfg.remote_base_folder = "My Photos"
    save_config(cfg)

    reloaded = load_config(tmp_path)
    assert reloaded.client_id == "abc-123"
    assert reloaded.remote_base_folder == "My Photos"


def test_derived_paths(tmp_path):
    cfg = load_config(tmp_path)
    assert cfg.token_cache_path.name == "token_cache.bin"
    assert cfg.manifest_path.name == "manifest.db"
    assert cfg.log_path.name == "backup.log"


def test_unknown_keys_ignored(tmp_path):
    (tmp_path / "config.json").write_text('{"client_id": "x", "bogus": 1}')
    cfg = load_config(tmp_path)
    assert cfg.client_id == "x"
