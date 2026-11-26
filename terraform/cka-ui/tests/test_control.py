import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"runner"))
from control import Controller,Problem,SCENARIOS,Store,topology

class Provider:
    def __init__(self):self.vms=[]
    def inventory(self):return list(self.vms)
    def capacity(self):return {"memoryFreeMiB":65536,"cpuCount":32}

class Executor:
    def __call__(self,action,lab,stage):
        stage("Diagnostic privé qui ne doit pas apparaître côté candidat")
        if action=="verify":return {"passed":True,"checks":[{"label":"Objectif atteint","passed":True}]}

ACTOR="a"*64
OTHER_ACTOR="b"*64

class AuthenticatedController(Controller):
    def submit(self,body,actor=ACTOR):return super().submit(body,actor)
    def status(self,actor=ACTOR):return super().status(actor)

class Contract(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.provider=Provider()
        self.controller=AuthenticatedController(Store(self.directory.name),self.provider,Executor())
    def test_scenario_determines_topology(self):
        self.controller.submit({"action":"create","scenario":"ha-controlplane"})
        lab,_=self.controller.store.read()
        self.assertEqual((lab["controlPlanes"],lab["workers"]),(3,2))
        self.assertEqual(len(lab["nodes"]),5)
        self.assertEqual(lab["scenario"],"ha-controlplane")
    def test_manual_topology_rejected(self):
        for body in [
            {"action":"create","controlPlanes":3,"workers":3},
            {"action":"create","scenario":"service","workers":1},
            {"action":"create","scenario":"service","profile":"bare"},
            {"action":"prepare","scenario":"service"},
            {"action":"create","scenario":"unknown"},
        ]:
            with self.assertRaises(Problem):self.controller.submit(body)
        self.assertIsNone(self.controller.store.read()[0])
    def test_single_lab_even_with_concurrent_submissions(self):
        results=[]
        def submit():
            try:self.controller.submit({"action":"create","scenario":"service"});results.append("created")
            except Problem:results.append("blocked")
        threads=[threading.Thread(target=submit) for _ in range(4)]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        self.assertEqual(results.count("created"),1)
        self.assertEqual(results.count("blocked"),3)
    def test_legacy_and_orphans_block_creation(self):
        for vms in [[{"vmid":620,"name":"k8s-master"}],[{"vmid":710,"name":"cka-cp-1"}]]:
            self.provider.vms=vms
            with self.assertRaises(Problem):self.controller.submit({"action":"create","scenario":"service"})
        self.assertIsNone(self.controller.store.read()[0])
    def test_public_view_has_no_preparation_or_private_stage(self):
        job=self.controller.submit({"action":"create","scenario":"service"})
        self.controller.store.stage(job["jobId"],"Secret de préparation : cause de la panne")
        status=self.controller.status()
        self.assertNotIn("cause de la panne",json.dumps(status))
        self.assertNotIn("topologies",status)
        self.assertNotIn("validation",status["lab"]["question"])
        for scenario in status["scenarios"]:
            self.assertFalse({"setup","hints","solution","correction"}.intersection(scenario))
    def test_verification_finishes_attempt(self):
        self.controller.submit({"action":"create","scenario":"service"})
        self.controller.execute_one()
        lab,_=self.controller.store.read()
        self.assertIn("readyAt",lab)
        self.controller.submit({"action":"verify","labId":lab["id"]})
        self.controller.execute_one()
        lab,_=self.controller.store.read()
        self.assertTrue(lab["finished"])
        self.assertTrue(lab["validation"]["passed"])
        with self.assertRaises(Problem):self.controller.submit({"action":"verify","labId":lab["id"]})
    def test_destruction_requires_exact_confirmation(self):
        self.controller.submit({"action":"create","scenario":"service"})
        self.controller.execute_one()
        lab,_=self.controller.store.read()
        for confirmation in ("","DETRUIRE 620,621","DETRUIRE 700,710"):
            with self.assertRaises(Problem):self.controller.submit({"action":"destroy","labId":lab["id"],"confirmation":confirmation})
        self.assertEqual(self.controller.store.read()[0]["status"],"ready")
    def test_catalog_prerequisites_fit_reserved_range(self):
        for key,scenario in SCENARIOS.items():
            plan=topology(scenario["controlPlanes"],scenario["workers"])
            self.assertGreaterEqual(len(plan["nodes"]),2,key)
            self.assertEqual(len(plan["vmids"]),len(set(plan["vmids"])),key)
            self.assertTrue(scenario["mission"],key)
    def test_invalid_capacity_is_not_silently_reduced(self):
        self.provider.capacity=lambda:{"memoryFreeMiB":1024,"cpuCount":32}
        with self.assertRaises(Problem):self.controller.submit({"action":"create","scenario":"ha-controlplane"})
        self.assertIsNone(self.controller.store.read()[0])

    def test_retry_preserves_lab_identity_and_topology(self):
        def fail_creation(action,lab,stage):
            if action=="create":raise RuntimeError("Temporary preflight failure")
        self.controller.executor=fail_creation
        self.controller.submit({"action":"create","scenario":"service"})
        self.controller.execute_one()
        before,_=self.controller.store.read()
        self.assertEqual(before["status"],"error")
        self.controller.submit({"action":"retry","labId":before["id"]})
        pending,_=self.controller.store.read()
        self.assertEqual(pending["id"],before["id"])
        self.assertEqual(pending["vmids"],before["vmids"])
        self.controller.execute_one()
        after,_=self.controller.store.read()
        self.assertEqual(after["status"],"ready")

    def test_retry_is_not_a_second_creation_or_evaluation(self):
        self.controller.submit({"action":"create","scenario":"service"})
        self.controller.execute_one()
        lab,_=self.controller.store.read()
        with self.assertRaises(Problem):self.controller.submit({"action":"retry","labId":lab["id"]})
        self.controller.submit({"action":"verify","labId":lab["id"]})
        self.controller.execute_one()
        with self.assertRaises(Problem):self.controller.submit({"action":"retry","labId":lab["id"]})

    def test_executor_retry_never_calls_terraform_or_replaces_a_vm(self):
        from provision import Executor as RealExecutor
        executor=RealExecutor(Path(__file__).resolve().parents[1],self.directory.name,"unused","unused")
        events=[]
        executor.assert_vm=lambda lab,vmid:events.append(("identity",vmid))
        executor.ssh=lambda *args,**kwargs:b"bare"
        executor.run=lambda *args,**kwargs:b""
        executor.start_assigned=lambda lab,vmid:None
        executor.pin=lambda *args:None
        executor.isolation=lambda lab:events.append(("isolation",None))
        executor.bootstrap=lambda lab,stage:events.append(("bootstrap",None))
        executor.initialize_exercise=lambda lab,stage:events.append(("exercise",None))
        executor.validate_cluster=lambda lab,stage:None
        def forbidden(*args,**kwargs):raise AssertionError("Terraform must not run during retry")
        executor.terraform=forbidden
        lab={"id":"00000000-0000-0000-0000-000000000001",**topology(1,2),"scenario":"service"}
        executor("retry",lab,lambda stage:None)
        self.assertEqual([value for kind,value in events if kind=="identity"],lab["vmids"])
        self.assertEqual([kind for kind,_ in events][-3:],["isolation","bootstrap","exercise"])

    def test_destroy_plan_keeps_shared_image_pool_and_storage(self):
        from provision import Executor as RealExecutor
        executor=RealExecutor(Path(__file__).resolve().parents[1],self.directory.name,"unused","unused")
        lab={"id":"00000000-0000-0000-0000-000000000001",**topology(1,1),"scenario":"service"}
        executor.vars=lambda lab,start:Path(self.directory.name)/"vars.json"
        calls=[]
        plan={"resource_changes":[{"type":"proxmox_virtual_environment_vm","change":{"actions":["delete"],"before":{"vm_id":710,"name":"cka-cp-1"}}},{"type":"proxmox_virtual_environment_file","change":{"actions":["delete"],"before":{"id":"cka-ui-snippets:snippets/"+lab["id"]+"-cka-cp-1-cloud-init.yaml"}}}]}
        def run(argv,**kwargs):
            calls.append(argv)
            return json.dumps(plan).encode() if "show" in argv else b""
        executor.run=run
        executor.terraform("destroy",lab,lambda stage:None,start=True)
        target_args=next(args for args in calls if "plan" in args)
        self.assertIn("-target=proxmox_virtual_environment_vm.guest",target_args)
        self.assertIn("-target=proxmox_virtual_environment_file.cloud_init",target_args)
        self.assertFalse(any("proxmox_download_file" in arg or "proxmox_storage_directory" in arg or "proxmox_virtual_environment_pool" in arg for arg in target_args))
        self.assertTrue(any("apply" in args for args in calls))

    def test_destroy_refuses_common_resource_or_foreign_snippet(self):
        from provision import Executor as RealExecutor
        for change in [
            {"type":"proxmox_download_file","change":{"actions":["delete"],"before":{}}},
            {"type":"proxmox_virtual_environment_file","change":{"actions":["delete"],"before":{"id":"another-session.yaml"}}},
        ]:
            executor=RealExecutor(Path(__file__).resolve().parents[1],self.directory.name,"unused","unused")
            lab={"id":"00000000-0000-0000-0000-000000000001",**topology(1,1),"scenario":"service"}
            executor.vars=lambda lab,start:Path(self.directory.name)/"vars.json"
            calls=[]
            def run(argv,**kwargs):
                calls.append(argv)
                return json.dumps({"resource_changes":[change]}).encode() if "show" in argv else b""
            executor.run=run
            with self.assertRaises(RuntimeError):executor.terraform("destroy",lab,lambda stage:None,start=True)
            self.assertFalse(any("apply" in args for args in calls))

if __name__=="__main__":unittest.main()
