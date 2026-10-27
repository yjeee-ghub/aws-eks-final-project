"""First deployment of foundation only. Does not apply DNS, app or messaging.

Each apply consumes an inspected saved plan and rejects deletion/update/foreign
resource types. Full-stack reconciliation remains a separate later operation.
Logs/plans/evidence live under the ignored .lab directory.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import urllib.request
import ipaddress
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / '.lab/foundation'
EVIDENCE = ROOT/'_ppt_src/02_인프라와_운영_기반/검증로그'/datetime.now(timezone(timedelta(hours=9))).strftime('%Y%m%d')
CONFIG = json.loads((ROOT/'scripts/ops/environment.json').read_text(encoding='utf-8'))
TARGETS = ('module.network','module.iam','module.eks','module.rds','module.ecr','module.ebs_csi','aws_eks_addon.metrics_server')

def run(args, label):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    (FOLDER/(label+'.log')).write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
    # State/plan JSON stays private in .lab; ordinary execution logs go to PPT sources.
    if not label.endswith('-show'):
        EVIDENCE.mkdir(parents=True,exist_ok=True)
        (EVIDENCE/(label+'.log')).write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
    if result.returncode:
        print((result.stdout+result.stderr)[-5500:])
        raise RuntimeError(label+' failed')
    return result.stdout

def aws(*args):
    return json.loads(run(['aws',*args,'--profile',CONFIG['profile'],'--region',CONFIG['region'],'--output','json','--no-cli-pager'],'aws-'+args[1]))

def identity():
    caller=aws('sts','get-caller-identity')
    expected='arn:aws:iam::'+CONFIG['account']+':user/512-team01'
    if caller['Account']!=CONFIG['account'] or caller['Arn']!=expected:
        raise ValueError('Account/principal mismatch')

def plan(root, stage, extra):
    path=FOLDER/(stage+'.tfplan')
    run(['terraform','-chdir='+root,'plan','-input=false','-no-color','-out='+str(path),*extra],stage+'-plan')
    value=json.loads(run(['terraform','-chdir='+root,'show','-json',str(path)],stage+'-show'))
    changes=[c for c in value.get('resource_changes',[]) if c.get('mode','managed')=='managed' and c['change']['actions']!=['no-op']]
    if not changes or any(c['change']['actions']!=['create'] for c in changes):
        raise ValueError('Initial plan must contain creates only')
    for c in changes:
        if stage=='bootstrap':
            if not c['type'].startswith('aws_s3_'):raise ValueError('Unexpected bootstrap change')
        elif not any(c['address'].startswith(t+'.') or c['address']==t for t in TARGETS):
            raise ValueError('Unexpected foundation target: '+c['address'])
    summary={'count':len(changes),'changes':[{'address':c['address'],'actions':c['change']['actions']} for c in changes]}
    (FOLDER/(stage+'-summary.json')).write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('step',choices=['prepare','bootstrap-plan','bootstrap-apply','infra-plan','infra-apply','verify-plan']);args=parser.parse_args()
    FOLDER.mkdir(parents=True,exist_ok=True);identity()
    if args.step=='prepare':
        with urllib.request.urlopen('https://checkip.amazonaws.com',timeout=15) as r:ip=ipaddress.ip_address(r.read(100).decode().strip())
        if ip.version!=4 or not ip.is_global:raise ValueError('Public IPv4 required')
        values={'eks_admin_principal_arn':'arn:aws:iam::'+CONFIG['account']+':user/512-team01','eks_public_access_cidrs':[str(ip)+'/32'],'manage_db_password':True,'keep_legacy_node_group':False,'customer_email_sender':'','customer_email_enabled':False,'enable_website_dns':False,'enable_management_dns':False}
        # Persistent ignored settings keep later plans on the same CIDR.
        target=ROOT/'terraform/terraform.tfvars.json'
        if target.exists() and json.loads(target.read_text())!=values:raise ValueError('Existing local variables differ; review before overwrite')
        target.write_text(json.dumps(values,indent=2)+'\n',encoding='utf-8')
        print('Prepared foundation variables for '+CONFIG['account']+'; restricted public API CIDR recorded.')
    elif args.step=='bootstrap-plan':
        run(['terraform','-chdir=terraform-state-bootstrap','init','-input=false','-no-color'],'bootstrap-init')
        plan('terraform-state-bootstrap','bootstrap',[])
    elif args.step=='infra-plan':
        run(['terraform','-chdir=terraform','init','-reconfigure','-input=false','-no-color'],'infra-init')
        plan('terraform','infra',['-target='+t for t in TARGETS])
    elif args.step in ('bootstrap-apply','infra-apply'):
        stage=args.step.split('-')[0];root='terraform-state-bootstrap' if stage=='bootstrap' else 'terraform'
        path=FOLDER/(stage+'.tfplan')
        # Recheck the exact saved plan, including targets, immediately before apply.
        value=json.loads(run(['terraform','-chdir='+root,'show','-json',str(path)],stage+'-apply-show'))
        changes=[c for c in value.get('resource_changes',[]) if c.get('mode','managed')=='managed' and c['change']['actions']!=['no-op']]
        if not changes or any(c['change']['actions']!=['create'] for c in changes):raise ValueError('Saved plan is not create-only')
        print(run(['terraform','-chdir='+root,'apply','-input=false','-no-color',str(path)],stage+'-apply')[-6500:])
    else:
        output=run(['terraform','-chdir=terraform','plan','-input=false','-no-color','-detailed-exitcode',*['-target='+t for t in TARGETS]],'foundation-recheck')
        print(output[-1500:])

if __name__=='__main__':main()
