"""Collect foundation evidence and test private-node/DB connectivity.

Passwords are retrieved only into memory and submitted to a short-lived K8s
Secret on stdin. Secret data and raw AWS secret responses are never logged.
"""
import base64
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import subprocess
import shlex
import time

ROOT=Path(__file__).resolve().parents[2]
CONFIG=json.loads((ROOT/'scripts/ops/environment.json').read_text(encoding='utf-8'))
FOLDER=ROOT/'_ppt_src/02_인프라와_운영_기반/검증로그'/datetime.now(timezone(timedelta(hours=9))).strftime('%Y%m%d')
NS='foundation-verify'

def command(args,*,payload=None,timeout=120):
    result=subprocess.run(args,cwd=ROOT,input=payload,capture_output=True,text=True,encoding='utf-8',timeout=timeout)
    if result.returncode:
        # Do not echo request bodies or arbitrary CLI diagnostic strings.
        raise RuntimeError(f'{args[0]} {args[1]} failed (exit {result.returncode})')
    return result.stdout

def save(name,value):
    (FOLDER/name).write_text(json.dumps(value,indent=2,ensure_ascii=False) if not isinstance(value,str) else value,encoding='utf-8')
    return value

def aws(*args):
    return json.loads(command(['aws',*args,'--profile',CONFIG['profile'],'--region',CONFIG['region'],'--output','json','--no-cli-pager']))

def kube(*args,**kwargs):return command(['kubectl','--context',CONFIG['cluster'],*args],**kwargs)

def apply(value):return kube('apply','-f','-',payload=json.dumps(value))

def probe(name,image,cmd,*,node=None,zone=None,secret=False):
    container={'name':'check','image':image,'command':cmd,'resources':{'requests':{'cpu':'50m','memory':'64Mi'},'limits':{'memory':'256Mi'}}}
    if secret:container['env']=[{'name':key,'valueFrom':{'secretKeyRef':{'name':'db-probe','key':key}}} for key in ['MYSQL_PWD','DB_HOST']]
    spec={'restartPolicy':'Never','automountServiceAccountToken':False,'containers':[container]}
    if node:spec['nodeName']=node
    if zone:spec['nodeSelector']={'topology.kubernetes.io/zone':zone}
    apply({'apiVersion':'v1','kind':'Pod','metadata':{'name':name,'namespace':NS,'labels':{'purpose':'foundation-verification'}},'spec':spec})
    deadline=time.monotonic()+300
    while time.monotonic()<deadline:
        pod=json.loads(kube('get','pod',name,'-n',NS,'-o','json'))
        phase=pod.get('status',{}).get('phase')
        if phase in ('Succeeded','Failed'):
            save(name+'-pod.json',pod)
            output=kube('logs',name,'-n',NS)
            save(name+'.log',output)
            if phase!='Succeeded':raise RuntimeError(name+' failed; inspect recorded pod events/logs')
            print(name+': '+output.strip(),flush=True)
            return output
        time.sleep(4)
    save(name+'-timeout.json',json.loads(kube('get','pod',name,'-n',NS,'-o','json')))
    raise TimeoutError(name+' did not complete within 300 seconds')

def main():
    FOLDER.mkdir(parents=True,exist_ok=True)
    identity=aws('sts','get-caller-identity')
    if identity['Account']!=CONFIG['account']:raise ValueError('Wrong account')
    save('01-identity.json',identity)
    cluster=save('02-cluster.json',aws('eks','describe-cluster','--name',CONFIG['cluster']))['cluster']
    if cluster['status']!='ACTIVE':raise ValueError('Cluster not ACTIVE')
    command(['aws','eks','update-kubeconfig','--name',CONFIG['cluster'],'--alias',CONFIG['cluster'],'--profile',CONFIG['profile'],'--region',CONFIG['region']])
    nodes=save('03-nodes.json',json.loads(kube('get','nodes','-o','json')))['items']
    if len(nodes)!=3 or not all(any(c['type']=='Ready' and c['status']=='True' for c in n['status']['conditions']) for n in nodes):raise ValueError('Expected three Ready nodes')
    save('03-nodes-wide.txt',kube('get','nodes','-o','wide'))
    save('04-system-pods.txt',kube('get','pods','-n','kube-system','-o','wide'))
    save('05-admin-access.json',aws('eks','list-associated-access-policies','--cluster-name',CONFIG['cluster'],'--principal-arn','arn:aws:iam::'+CONFIG['account']+':user/512-team01'))
    vpc=cluster['resourcesVpcConfig']['vpcId']
    save('06-vpc.json',aws('ec2','describe-vpcs','--vpc-ids',vpc))
    save('07-subnets.json',aws('ec2','describe-subnets','--filters','Name=vpc-id,Values='+vpc))
    save('08-route-tables.json',aws('ec2','describe-route-tables','--filters','Name=vpc-id,Values='+vpc))
    nat=save('09-nat.json',aws('ec2','describe-nat-gateways','--filter','Name=vpc-id,Values='+vpc))
    expected_ips={a['PublicIp'] for n in nat['NatGateways'] if n['State']=='available' for a in n['NatGatewayAddresses'] if 'PublicIp' in a}
    save('10-instances.json',aws('ec2','describe-instances','--filters','Name=vpc-id,Values='+vpc))
    db=save('11-database.json',aws('rds','describe-db-instances','--db-instance-identifier',CONFIG['database']))['DBInstances'][0]
    if db['DBInstanceStatus']!='available' or db['PubliclyAccessible']:raise ValueError('Expected available private DB')
    save('12-db-security-group.json',aws('ec2','describe-security-groups','--group-ids',*[s['VpcSecurityGroupId'] for s in db['VpcSecurityGroups']]))
    save('13-ecr.json',aws('ecr','describe-repositories'))
    save('14-state-versioning.json',aws('s3api','get-bucket-versioning','--bucket',CONFIG['stateBucket']))
    save('14-state-encryption.json',aws('s3api','get-bucket-encryption','--bucket',CONFIG['stateBucket']))
    save('14-state-public-access.json',aws('s3api','get-public-access-block','--bucket',CONFIG['stateBucket']))
    save('14-state-objects.json',aws('s3api','list-objects-v2','--bucket',CONFIG['stateBucket']))
    for addon in ['aws-ebs-csi-driver','metrics-server']:
        result=save('15-'+addon+'.json',aws('eks','describe-addon','--cluster-name',CONFIG['cluster'],'--addon-name',addon))
        if result['addon']['status']!='ACTIVE':raise ValueError('Addon not ACTIVE: '+addon)
    for group in aws('eks','list-nodegroups','--cluster-name',CONFIG['cluster'])['nodegroups']:
        save('16-'+group+'.json',aws('eks','describe-nodegroup','--cluster-name',CONFIG['cluster'],'--nodegroup-name',group))
    # Never adopt/delete an existing namespace or its workloads.
    existing=json.loads(kube('get','namespaces','-o','json'))
    if any(n['metadata']['name']==NS for n in existing['items']):raise ValueError('Probe namespace already exists; inspect before retry')
    kube('create','namespace',NS)
    completed=False
    try:
        network_code="import socket,urllib.request; print('DNS_OK',socket.gethostbyname('checkip.amazonaws.com')); print('NAT_EGRESS_IP',urllib.request.urlopen('https://checkip.amazonaws.com',timeout=20).read().decode().strip())"
        for i,node in enumerate(nodes):
            output=probe('network-'+str(i+1),'public.ecr.aws/docker/library/python:3.12-alpine',['python','-c',network_code],node=node['metadata']['name'])
            observed=next((line.split()[-1] for line in output.splitlines() if line.startswith('NAT_EGRESS_IP ')),None)
            if observed not in expected_ips:raise ValueError('Outbound IP does not match project NAT')
        secret=json.loads(aws('secretsmanager','get-secret-value','--secret-id',db['MasterUserSecret']['SecretArn'])['SecretString'])
        encoded={key:base64.b64encode(value.encode()).decode() for key,value in {'MYSQL_PWD':secret['password'],'DB_HOST':db['Endpoint']['Address']}.items()}
        apply({'apiVersion':'v1','kind':'Secret','metadata':{'name':'db-probe','namespace':NS},'type':'Opaque','data':encoded})
        del secret,encoded
        sql="SELECT 'DB_CONNECTION_OK' AS result, VERSION() AS mysql_version, DATABASE() AS db_name, @@hostname AS db_host; SHOW SESSION STATUS LIKE 'Ssl_cipher';"
        for zone in ['ap-northeast-2a','ap-northeast-2c']:
            output=probe('database-'+zone[-2:],'public.ecr.aws/docker/library/mysql:8.4',['sh','-c','exec mysql --connect-timeout=20 --ssl-mode=REQUIRED -h "$DB_HOST" -u admin ordermsa -e '+shlex.quote(sql)],zone=zone,secret=True)
            if 'DB_CONNECTION_OK' not in output:raise ValueError('Missing successful database marker')
        completed=True
    finally:
        # Probe namespace created by this execution only; remove credentials immediately.
        kube('delete','namespace',NS,'--wait=true','--timeout=120s',timeout=150)
    save('00-summary.json',{'status':'PASS' if completed else 'FAIL','account':CONFIG['account'],'cluster':CONFIG['cluster'],'vpcId':vpc,'nodesReady':3,'networkProbes':3,'dbProbeZones':['ap-northeast-2a','ap-northeast-2c'],'probeNamespaceRemoved':True,'verifiedAt':datetime.now(timezone.utc).isoformat()})
    print('PASS: foundation, three-node outbound NAT and encrypted DB connectivity from both AZs. Probe namespace removed.')

if __name__=='__main__':main()
