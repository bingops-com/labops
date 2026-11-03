#!/usr/bin/env python3
"""Hibernate only the six accepted migration copies; retain all CRs and PVCs."""
import argparse,json,subprocess
COPIES=(('games','arcade-games-restore-rehearsal'),('slots','arcade-slots-restore-rehearsal'),('games','arcade-postgresql-rehearsal'),('games','arcade-games-restore'),('slots','arcade-slots-restore'),('games','arcade-common-restore'))
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true',required=True);parser.parse_args()
 # A completed common backup and healthy actual consumer are prerequisites.
 for name in ['games','slots']:
  d=json.loads(subprocess.check_output(['kubectl','--context','labprod','-n',name,'get','deployment',name,'-o','json']))
  assert d['status'].get('readyReplicas',0)==1
  variable=name.upper()+'_SHARED_ACCOUNTS';assert any(e.get('name')==variable and e.get('value')=='true' for c in d['spec']['template']['spec']['containers'] for e in c.get('env',[]))
 backup=json.loads(subprocess.check_output(['kubectl','--context','labprod','-n','games','get','backup','cka-common-accepted-20261103','-o','json']))
 assert backup['status']['phase']=='completed'
 for namespace,cluster in COPIES:
  subprocess.run(['kubectl','--context','labprod','-n',namespace,'annotate','cluster',cluster,'cnpg.io/hibernation=on','--overwrite'],check=True)
 print('Migration copies hibernating; common production database, source clusters and all persistent volumes retained.')
if __name__=='__main__':main()
