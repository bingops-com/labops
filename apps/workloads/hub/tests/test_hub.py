"""Offline cutover checks: public directory must never expose the private portal."""
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import unittest
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]


@lru_cache
def render(path):
    result = subprocess.run(["kubectl", "kustomize", str(REPO / path)],
                            check=True, capture_output=True, text=True)
    return list(yaml.safe_load_all(result.stdout))


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.scripts = []
        self.current_access = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "li" and "data-service" in attrs:
            self.current_access = attrs["data-access"]
        if tag == "a":
            self.links.append((attrs.get("href", ""), self.current_access))
        if tag == "script":
            self.scripts.append(attrs)

    def handle_endtag(self, tag):
        if tag == "li":
            self.current_access = None


class HubIsolationTests(unittest.TestCase):
    def test_public_and_private_routes_are_separate(self):
        hub = render("apps/workloads/hub/clusters/labprod")
        portal = render("apps/workloads/portal/clusters/labprod")
        public_ingress = next(x for x in hub if x["kind"] == "Ingress")
        private_ingress = next(x for x in portal if x["kind"] == "Ingress")
        self.assertEqual(public_ingress["spec"]["rules"][0]["host"], "lab.bingo")
        self.assertEqual(private_ingress["spec"]["rules"][0]["host"], "portal.lab.bingo")
        self.assertIn("portal-allowlist", private_ingress["metadata"]["annotations"]
                      ["traefik.ingress.kubernetes.io/router.middlewares"])
        tunnel = yaml.safe_load((REPO / "apps/cloudflare/bingops/values.yaml").read_text())
        routes = tunnel["cloudflare"]["ingress"]
        self.assertEqual([r["service"] for r in routes if r["hostname"] == "lab.bingo"],
                         ["http://hub.hub.svc.cluster.local:80"])
        self.assertFalse(any("portal.portal.svc" in r["service"] for r in routes))
        self.assertNotIn("portal.lab.bingo", [r["hostname"] for r in routes])
        deployment = next(x for x in portal if x["kind"] == "Deployment")
        env = {e["name"]: e.get("value") for e in deployment["spec"]["template"]["spec"]["containers"][0]["env"]}
        self.assertEqual(env["PORTAL_PUBLIC_URL"], "https://portal.lab.bingo")
        bp = yaml.safe_load((REPO / "apps/platform/authentik/blueprint.yaml").read_text())
        self.assertIn("url: https://portal.lab.bingo/auth/callback", bp["data"]["argocd.yaml"])
        self.assertNotIn("url: https://lab.bingo/auth/callback", bp["data"]["argocd.yaml"])
        dns = yaml.safe_load((REPO / "apps/platform/private-dns/labprod/configmap.yaml").read_text())
        self.assertIn("portal.lab.bingo:53", dns["data"]["Corefile"])

    def test_public_site_has_no_server_identity_or_durable_state(self):
        hub = render("apps/workloads/hub/clusters/labprod")
        self.assertFalse(any(x["kind"] in {"Secret", "PersistentVolumeClaim", "ClusterRoleBinding"} for x in hub))
        deployment = next(x for x in hub if x["kind"] == "Deployment")
        pod = deployment["spec"]["template"]["spec"]
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertTrue(pod["securityContext"]["runAsNonRoot"])
        self.assertTrue(pod["containers"][0]["securityContext"]["readOnlyRootFilesystem"])
        config = (ROOT / "base/Caddyfile").read_text()
        self.assertIn("connect-src 'none'", config)
        self.assertIn("admin off", config)
        for cm in (x for x in hub if x["kind"] == "ConfigMap"):
            self.assertLess(len(yaml.safe_dump(cm)), 900_000)

    def test_catalogue_links_are_https_and_private_services_are_labelled(self):
        parser = Links()
        parser.feed((ROOT / "base/site/index.html").read_text())
        services = [(urlsplit(url), access) for url, access in parser.links if access]
        self.assertEqual(len(services), 14)
        self.assertEqual(len({url.hostname for url, _ in services}), 14)
        private = {"portal.lab.bingo", "coder.lab.bingo", "dev.lab.bingo", "argocd.lab.bingo", "grafana.lab.bingo"}
        for url, access in services:
            self.assertEqual(url.scheme, "https")
            self.assertFalse(url.username or url.password or url.query or url.port)
            self.assertTrue(url.hostname.endswith(".lab.bingo") or url.hostname.endswith(".bingops.com"))
            if url.hostname in private:
                self.assertEqual(access, "private")
        self.assertTrue(all(s.get("src", "").startswith("/") for s in parser.scripts))


if __name__ == "__main__":
    unittest.main()
