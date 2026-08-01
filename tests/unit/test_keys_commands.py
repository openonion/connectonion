from connectonion import address
from connectonion.cli.commands import keys_commands

PHRASE = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"


def _key_data():
    keys = address.derive_ssh_key(PHRASE)
    return {"seed_phrase": PHRASE}, keys


def test_write_keeps_matching_derived_key(tmp_path, monkeypatch):
    addr_data, keys = _key_data()
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir()
    private_path = ssh_dir / "connectonion_ed25519"
    public_path = ssh_dir / "connectonion_ed25519.pub"
    private_path.write_text(keys["private_key"])
    public_path.write_text(keys["public_line"] + "\n")

    monkeypatch.setattr(keys_commands.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(keys_commands, "_public_key_from_private", lambda path: keys["public_line"])
    keys_commands._show_ssh_key(addr_data, write=True)

    assert private_path.read_text() == keys["private_key"]
    assert public_path.read_text() == keys["public_line"] + "\n"
    assert not (ssh_dir / "connectonion_ed25519.bak").exists()


def test_write_backs_up_and_replaces_mismatched_key(tmp_path, monkeypatch):
    addr_data, keys = _key_data()
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir()
    private_path = ssh_dir / "connectonion_ed25519"
    public_path = ssh_dir / "connectonion_ed25519.pub"
    private_path.write_text("old private key\n")
    public_path.write_text("ssh-ed25519 OLD old\n")

    monkeypatch.setattr(keys_commands.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(keys_commands, "_public_key_from_private", lambda path: "ssh-ed25519 OLD old")
    keys_commands._show_ssh_key(addr_data, write=True)

    assert (ssh_dir / "connectonion_ed25519.bak").read_text() == "old private key\n"
    assert (ssh_dir / "connectonion_ed25519.pub.bak").read_text() == "ssh-ed25519 OLD old\n"
    assert private_path.read_text() == keys["private_key"]
    assert public_path.read_text() == keys["public_line"] + "\n"
