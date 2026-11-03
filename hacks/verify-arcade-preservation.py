#!/usr/bin/env python3
"""Compare restored Arcade source data to the common target without logging rows."""
import json,os,subprocess

def rows(service,sql):
 result=subprocess.run(['psql','-X','-At','-v','ON_ERROR_STOP=1','-c',sql],env={**os.environ,'PGSERVICE':service},capture_output=True,text=True)
 if result.returncode:raise RuntimeError('Private database comparison failed; no row was logged')
 return [json.loads(line) for line in result.stdout.splitlines() if line]

def main():
 target=os.environ['ARCADE_TARGET_SERVICE']
 links=rows(target,"SELECT json_build_object('source',source_app,'sourceId',source_user_id,'accountId',account_id) FROM identity.account_links")
 mapping={(r['source'],r['sourceId']):r['accountId'] for r in links}
 users={r['id']:r for r in rows(target,'SELECT row_to_json(u) FROM identity.users u')}
 counts={}
 for app in ('games','slots'):
  service=os.environ['ARCADE_'+app.upper()+'_RESTORE_SERVICE']
  sources=rows(service,f'SELECT row_to_json(u) FROM {app}.users u')
  for source in sources:
   common=users[mapping[(app,source['id'])]]
   for key,value in source.items():
    if key=='id':continue
    if key=='name_key':
     if common[key] not in (value,'slots:'+value):raise RuntimeError('Login alias conservation failed')
    elif key not in common or common[key]!=value:raise RuntimeError('Account conservation failed; values withheld')
  source_stats=rows(service,f'SELECT row_to_json(s) FROM {app}.game_stats s')
  expected=[]
  for row in source_stats:
   if 'user_id' in row:row['user_id']=mapping[(app,row['user_id'])]
   expected.append(json.dumps(row,sort_keys=True))
  actual=[json.dumps(row,sort_keys=True) for row in rows(target,f'SELECT row_to_json(s) FROM {app}.game_stats s')]
  if sorted(expected)!=sorted(actual):raise RuntimeError('Game statistics conservation failed; values withheld')
  counts[app]=len(sources)
 if sum(counts.values())!=len(users) or len(mapping)!=len(users):raise RuntimeError('Unexpected account cardinality')
 print('Conservation verified: '+str(counts['games'])+' Games accounts, '+str(counts['slots'])+' Slots accounts, '+str(len(users))+' separate principals; original fields and statistics match.')
if __name__=='__main__':
 try:main()
 except Exception:raise SystemExit('Conservation check refused acceptance; no account data or credentials were displayed.')
