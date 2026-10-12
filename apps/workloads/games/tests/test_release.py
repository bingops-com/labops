import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from check_release import ReleaseError, extract_pins, fetch_json, verify_published


SHA = "a" * 40
DIGEST = "sha256:" + "b" * 64
APPLICATION = f"  sources:\n    - repoURL: https://github.com/bingops-com/games.git\n      targetRevision: {SHA}\n      path: chart\n"
VALUES = f"image:\n  repository: ghcr.io/bingops-com/games\n  tag: sha-{SHA}\n"


class ReleaseTests(unittest.TestCase):
    def test_mismatched_or_ambiguous_pins_are_rejected(self):
        self.assertEqual(extract_pins(APPLICATION, VALUES), SHA)
        for values in (VALUES.replace(SHA, "c" * 40), VALUES + VALUES, VALUES.replace("sha-" + SHA, "latest")):
            with self.assertRaises(ReleaseError):
                extract_pins(APPLICATION, values)

    def test_unmerged_commit_never_queries_registry(self):
        for status in ("behind", "diverged", None):
            with patch("check_release.fetch_json", return_value={"status": status}) as fetch:
                with self.assertRaisesRegex(ReleaseError, "not merged"):
                    verify_published(SHA)
                self.assertEqual(fetch.call_count, 1)

    def test_missing_image_is_rejected(self):
        with patch("check_release.fetch_json", side_effect=[{"status": "ahead"}, {"token": "synthetic-anonymous-token"}, ReleaseError("HTTP 404")]):
            with self.assertRaises(ReleaseError):
                verify_published(SHA)

    def test_public_image_and_separate_authentication(self):
        with patch.dict("os.environ", {"GH_TOKEN": "synthetic-ci-token"}):
            with patch("check_release.fetch_json", side_effect=[{"status": "identical"}, {"token": "synthetic-anonymous-token"}, {"config": {"digest": DIGEST}}, {"os": "linux", "architecture": "amd64"}]) as fetch:
                verify_published(SHA)
                self.assertEqual(fetch.call_args_list[0].args[1]["Authorization"], "Bearer synthetic-ci-token")
                self.assertEqual(len(fetch.call_args_list[1].args), 1)
                self.assertEqual(fetch.call_args_list[2].args[1]["Authorization"], "Bearer synthetic-anonymous-token")

    def test_wrong_architecture_or_digest_is_rejected(self):
        for manifest, config in (({"config": {"digest": DIGEST}}, {"os": "linux", "architecture": "arm64"}), ({"config": {"digest": "../../private"}}, {}), ({"manifests": []}, {})):
            with patch("check_release.fetch_json", side_effect=[{"status": "ahead"}, {"token": "synthetic-anonymous-token"}, manifest, config]):
                with self.assertRaises(ReleaseError):
                    verify_published(SHA)

    def test_multi_arch_image_selects_linux_amd64(self):
        index = {"manifests": [{"platform": {"os": "linux", "architecture": "amd64"}, "digest": DIGEST}]}
        with patch("check_release.fetch_json", side_effect=[{"status": "ahead"}, {"token": "synthetic-anonymous-token"}, index, {"config": {"digest": DIGEST}}, {"os": "linux", "architecture": "amd64"}]):
            verify_published(SHA)

    def test_blob_redirect_never_forwards_authorization(self):
        location = "https://pkg-containers.githubusercontent.com/synthetic-config?signature=synthetic"
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"os":"linux"}'
        opener = MagicMock()
        opener.open.side_effect = [urllib.error.HTTPError("https://ghcr.io/", 307, "redirect", {"Location": location}, None), response]
        with patch("check_release.urllib.request.build_opener", return_value=opener):
            self.assertEqual(fetch_json("https://ghcr.io/", {"Authorization": "Bearer synthetic-token"}, allow_blob_redirect=True), {"os": "linux"})
        self.assertNotIn("Authorization", opener.open.call_args_list[1].args[0].headers)

    def test_blob_redirect_rejects_untrusted_origins(self):
        for location in ("http://pkg-containers.githubusercontent.com/blob", "https://evil.example/blob", "https://pkg-containers.githubusercontent.com@evil.example/blob"):
            opener = MagicMock()
            opener.open.side_effect = urllib.error.HTTPError("https://ghcr.io/", 307, "redirect", {"Location": location}, None)
            with patch("check_release.urllib.request.build_opener", return_value=opener):
                with self.assertRaises(ReleaseError):
                    fetch_json("https://ghcr.io/", allow_blob_redirect=True)
            self.assertEqual(opener.open.call_count, 1)

    def test_metadata_redirects_and_repeated_redirects_are_rejected(self):
        redirect = urllib.error.HTTPError("https://ghcr.io/", 307, "redirect", {"Location": "https://pkg-containers.githubusercontent.com/blob"}, None)
        opener = MagicMock()
        opener.open.side_effect = redirect
        with patch("check_release.urllib.request.build_opener", return_value=opener):
            with self.assertRaises(ReleaseError):
                fetch_json("https://api.github.com/", {"Authorization": "Bearer synthetic-token"})
            self.assertEqual(opener.open.call_count, 1)
            with self.assertRaises(ReleaseError):
                fetch_json("https://ghcr.io/", allow_blob_redirect=True)
            self.assertEqual(opener.open.call_count, 3)


if __name__ == "__main__":
    unittest.main()
