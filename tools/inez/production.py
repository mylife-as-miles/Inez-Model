"""Local candidate/version ledger. Never generates images or assigns review scores."""
from pathlib import Path
from PIL import Image
import argparse, json, hashlib, shutil, datetime

ROOT = Path(__file__).resolve().parents[2]/'assets/characters/inez'
LEDGER = ROOT / 'qa/generation_ledger.json'

def main():
    p = argparse.ArgumentParser()
    p.add_argument('operation', choices=['begin', 'complete', 'approve', 'approve_geometry', 'fail', 'hold', 'reject'])
    p.add_argument('view')
    p.add_argument('--prompt')
    p.add_argument('--source')
    p.add_argument('--note', default='')
    p.add_argument('--version', type=int)
    a = p.parse_args()
    ledger = json.loads(LEDGER.read_text())
    if a.operation == 'begin':
        if len(ledger['calls']) >= ledger['cap']:
            raise SystemExit('24-call initial budget exhausted. No further generation authorized.')
        attempts = [x for x in ledger['calls'] if x['view'] == a.view]
        view_limit = ledger.get('per_view_call_limits', {}).get(a.view, 4)
        if len(attempts) >= view_limit:
            raise SystemExit('Authorized per-view call allowance exhausted for this view.')
        prompt = Path(a.prompt).resolve()
        if not prompt.is_file():
            raise SystemExit('Missing retained prompt')
        item = dict(call=len(ledger['calls'])+1, view=a.view, version=len(attempts)+1,
                    prompt=str(prompt.relative_to(ROOT.parents[2])),
                    sent_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    status='sent', anchors=['references/original/inez_portraits.jpg',
                                             'references/original/inez_turnaround.jpg'])
        for authorization in ledger.get('authorizations', []):
            if item['call'] in authorization.get('planned_call_numbers', []):
                item['authorization_id'] = authorization['id']
        ledger['calls'].append(item)
    else:
        item = next(x for x in reversed(ledger['calls']) if x['view'] == a.view and (a.version is None or x['version']==a.version))
        if a.operation == 'complete':
            src = Path(a.source)
            im = Image.open(src)
            dst = ROOT / 'references/generated' / (a.view + '_v%02d.png' % item['version'])
            if im.format == 'PNG':
                shutil.copy2(src, dst)
            else:
                im.save(dst)
            item.update(status='candidate', output=str(dst.relative_to(ROOT)),
                        size=list(im.size), sha256=hashlib.sha256(dst.read_bytes()).hexdigest())
        elif a.operation == 'fail':
            item.update(status='failed', note=a.note)
        elif a.operation in ('hold','reject'):
            item.update(status=a.operation, decision=a.note)
        else:
            if not a.note:
                raise SystemExit('Approval requires explicit review report paths/decision')
            src = ROOT / item['output']
            dst = ROOT / 'references/approved' / (a.view + '.png')
            shutil.copy2(src, dst)
            item.update(status='approved_geometry_only' if a.operation == 'approve_geometry' else 'approved_for_reference', decision=a.note,
                        approved_output=str(dst.relative_to(ROOT)))
    LEDGER.write_text(json.dumps(ledger, indent=2)+'\n')
    print(json.dumps(item, indent=2))

if __name__ == '__main__':
    main()
