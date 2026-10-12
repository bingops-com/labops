"""Offline Games OIDC authorization contract; requires PyYAML, no credentials."""

from pathlib import Path
from types import SimpleNamespace
import textwrap
import yaml


class BlueprintLoader(yaml.SafeLoader):
    pass


def reference(loader, tag, node):
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_scalar(node)


BlueprintLoader.add_multi_constructor("!", reference)
config = yaml.safe_load((Path(__file__).parents[1] / "blueprint.yaml").read_text())
blueprint = yaml.load(config["data"]["games-admin.yaml"], Loader=BlueprintLoader)
entries = {entry.get("id"): entry for entry in blueprint["entries"]}
provider = entries["games-admin-provider"]["attrs"]
assert provider["client_type"] == "public"
assert provider["grant_types"] == ["authorization_code"]
assert provider["redirect_uris"] == [
    {"matching_mode": "strict", "url": "https://games.lab.bingo/api/admin/callback"}
]
assert entries["games-admins"]["attrs"]["users"] == [
    ["authentik_core.user", ["username", "bingops"]]
]


class Groups(list):
    def filter(self, *, name):
        return Groups(group for group in self if group.name == name)

    def exists(self):
        return bool(self)


def function(entry):
    namespace = {}
    source = "def evaluate(user, request):\n" + textwrap.indent(
        entry["attrs"]["expression"], "    "
    )
    exec(compile(source, "games-admin-blueprint", "exec"), namespace)
    return namespace["evaluate"]


claims = function(entries["games-admin-scope"])
policy = function(entries["games-admin-policy"])
for name, active, member, allowed in [
    ("bingops", True, True, True),
    ("bingops", True, False, False),
    ("bingops", False, True, False),
    ("ordinary", True, True, False),
    ("akadmin", True, True, False),
]:
    groups = Groups([SimpleNamespace(name="games-admins")] if member else [])
    user = SimpleNamespace(
        username=name, is_active=active, is_authenticated=True, all_groups=lambda: groups
    )
    # Userinfo evaluates mappings with the token's user, independently of the
    # HTTP browser session. An unrelated request user must not influence claims.
    result = claims(user, SimpleNamespace(user=None))
    assert result["games_admin"] is allowed
    assert ("games-admins" in result["groups"]) is member
    assert policy(user, SimpleNamespace(user=user)) is allowed
print("Games Authentik: public code provider, strict callback, sole identity and current-role checks passed")
