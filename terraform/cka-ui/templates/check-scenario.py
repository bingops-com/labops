#!/usr/bin/env python3
"""State-based evaluation, executed only inside the attributed cluster."""
import json, subprocess, sys
scenario=sys.argv[1]
checks=[]
def call(args,timeout=20):
    return subprocess.run(["kubectl",*args],capture_output=True,text=True,timeout=timeout)
def obj(kind,name=None,ns=None):
    args=(["-n",ns] if ns else [])+["get",kind]+([name] if name else [])+["-o","json"]
    result=call(args)
    if result.returncode: return {}
    return json.loads(result.stdout)
def check(label,value):
    checks.append({"label":label,"passed":bool(value)})
def ready(deployment):
    return deployment.get("spec",{}).get("replicas",1)>0 and deployment.get("status",{}).get("availableReplicas",0)>=deployment.get("spec",{}).get("replicas",1)
def http(ns,service,client="probe"):
    result=call(["-n",ns,"exec",client,"--","wget","-T","4","-qO-","http://"+service],timeout=10)
    return result.returncode==0 and bool(result.stdout)
try:
    if scenario=="service":
        service=obj("service","web","cka-service")
        check("Service conservé",bool(service) and service.get("spec",{}).get("clusterIP") not in (None,"","None"))
        check("Application disponible",ready(obj("deployment","web","cka-service")))
        check("Accès HTTP depuis un client",http("cka-service","web"))
    elif scenario=="rollout":
        deployment=obj("deployment","api","cka-rollout")
        check("Trois réplicas disponibles",deployment.get("spec",{}).get("replicas")==3 and ready(deployment))
        check("Image de la révision précédente",any(c.get("image")=="nginx:1.28" for c in deployment.get("spec",{}).get("template",{}).get("spec",{}).get("containers",[])))
    elif scenario=="rbac":
        subject="--as=system:serviceaccount:cka-rbac:reader"
        for verb,resource,ns,want in [("get","pods","cka-rbac",True),("list","pods","cka-rbac",True),("watch","pods","cka-rbac",True),("delete","pods","cka-rbac",False),("get","secrets","cka-rbac",False),("list","pods","default",False)]:
            result=call(["auth","can-i",verb,resource,"-n",ns,subject])
            check(verb+" "+resource+" dans "+ns,result.stdout.strip()==("yes" if want else "no"))
    elif scenario=="schedule":
        deployment=obj("deployment","app","cka-schedule")
        check("Contrainte de placement conservée",deployment.get("spec",{}).get("template",{}).get("spec",{}).get("nodeSelector",{}).get("cka-disk")=="fast")
        check("Application disponible",ready(deployment))
        pods=obj("pods",ns="cka-schedule").get("items",[])
        check("Placement sur un worker",bool(pods) and all(p.get("spec",{}).get("nodeName","").startswith("cka-worker-") for p in pods if not p.get("metadata",{}).get("deletionTimestamp")))
    elif scenario=="probes":
        deployment=obj("deployment","web","cka-probes")
        containers=deployment.get("spec",{}).get("template",{}).get("spec",{}).get("containers",[])
        check("Probe HTTP conservée et fonctionnelle",any(c.get("readinessProbe",{}).get("httpGet",{}).get("port")==80 for c in containers))
        check("Application disponible",ready(deployment))
        check("Accès HTTP",http("cka-probes","web"))
    elif scenario=="pending-pvc":
        claim=obj("pvc","data","cka-pvc")
        check("PVC Bound",claim.get("status",{}).get("phase")=="Bound")
        quantity=claim.get("spec",{}).get("resources",{}).get("requests",{}).get("storage","")
        check("Demande de stockage conservée",quantity=="1Gi" and "ReadWriteOnce" in claim.get("spec",{}).get("accessModes",[]))
    elif scenario=="crashloop":
        deployment=obj("deployment","worker","cka-crash")
        check("Workload disponible",ready(deployment))
        observed=call(["-n","cka-crash","exec","deployment/worker","--","printenv","APP_MODE"])
        check("Configuration applicative fonctionnelle",observed.returncode==0 and observed.stdout.strip()=="ready")
        containers=deployment.get("spec",{}).get("template",{}).get("spec",{}).get("containers",[])
        check("Image et mécanisme de démarrage conservés",any(c.get("image")=="busybox:1.37" and c.get("command")==["sh","-c"] and any("APP_MODE" in arg for arg in c.get("args",[])) for c in containers))
        pods=obj("pods",ns="cka-crash").get("items",[])
        check("Conteneur stable",bool(pods) and all(s.get("restartCount",0)==0 for p in pods if not p.get("metadata",{}).get("deletionTimestamp") for s in p.get("status",{}).get("containerStatuses",[])))
    elif scenario=="kubelet":
        nodes=obj("nodes").get("items",[])
        check("Tous les nœuds attendus sont présents",len(nodes)==3)
        check("Tous les nœuds sont Ready",bool(nodes) and all(any(c.get("type")=="Ready" and c.get("status")=="True" for c in n.get("status",{}).get("conditions",[])) for n in nodes))
    elif scenario=="controlplane":
        deployment=obj("deployment","proof","cka-proof")
        check("Planification et exécution rétablies",ready(deployment))
        pods=obj("pods",ns="cka-proof").get("items",[])
        check("Nouveau Pod assigné à un worker",any(p.get("spec",{}).get("nodeName","").startswith("cka-worker-") for p in pods))
    elif scenario=="drain":
        node=obj("node","cka-worker-1")
        check("Nœud en maintenance",node.get("spec",{}).get("unschedulable") is True)
        deployment=obj("deployment","web","cka-drain")
        check("Trois réplicas disponibles",deployment.get("spec",{}).get("replicas")==3 and ready(deployment))
        pods=obj("pods",ns="cka-drain").get("items",[])
        workload=[p for p in pods if p.get("metadata",{}).get("labels",{}).get("app")=="web"]
        check("Workloads déplacés",len(workload)>=3 and all(p.get("spec",{}).get("nodeName")!="cka-worker-1" for p in workload))
        check("Budget de disponibilité conservé",obj("pdb","web","cka-drain").get("spec",{}).get("minAvailable")==2)
        check("Accès HTTP disponible",http("cka-drain","web"))
    elif scenario=="policy":
        check("Client autorisé",http("cka-policy","web","good"))
        check("Client non autorisé refusé",not http("cka-policy","web","bad"))
        policies=obj("networkpolicies",ns="cka-policy").get("items",[])
        check("Filtrage déclaré",bool(policies))
    elif scenario=="ha-controlplane":
        for index in (10,11,12):
            result=call(["--server=https://172.30.90."+str(index)+":6443","--request-timeout=5s","get","--raw=/readyz"],timeout=8)
            check("API du control plane "+str(index-9),result.returncode==0 and result.stdout.strip()=="ok")
    else:
        check("Scénario reconnu",False)
except Exception:
    check("Vérification de l’état réel",False)
print(json.dumps({"passed":bool(checks) and all(c["passed"] for c in checks),"checks":checks}))
