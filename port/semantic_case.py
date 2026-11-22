"""Private, case-specific immutable input validation for the v4 proposal.

This module only prepares factual bindings. It does not approve audit findings.
The helper commit binds this file, its one case configuration and certificate.
"""
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

if not __debug__:
    raise RuntimeError('Assertions must remain enabled.')

LEAN = 'leanprover/lean4:v4.36.0'
MATHLIB = 'fc4f59e577feb1a4956671bc04ac18aaaf8cd842'
POLICY = dict(commit='3e956370a34018cb518084553ad90befaa8eed1c',
    audit_script_sha256='f94052a41bdca049b3e91c9077ccf940b0cc5fe36b3e2767f78a64567ac5aae7',
    reused_audit_script_sha256='2e72631b47fccd5b8f7f41f17c634e708566e96f17d8ebc53c86f592745ab5d1')
PINS = dict(lean=LEAN, mathlib=MATHLIB, replay_pins_unchanged=dict(
    lean='leanprover/lean4:v4.33.1', mathlib='0df444a360eaa60ab8c11dca51a86af692955474'))
MODULE_PREFIX = 'Formalism.HermitianCurvature.'
MODULES = {
    'M145351': MODULE_PREFIX + 'HermitianCurvatureProofs.AdditiveCharacterPsi',
    'M145372': MODULE_PREFIX + 'HermitianCurvatureProofs.AffineChangeOfVariables',
    'M145556': MODULE_PREFIX + 'HermitianCurvatureProofs.ContinuousInvUpper',
    'M145580': MODULE_PREFIX + 'HermitianCurvatureProofs.CuspidalIrreducibleSubrep',
    'M146320': MODULE_PREFIX + 'HermitianCurvatureProofs.FourierUniquenessMirabolic',
    'M146727': MODULE_PREFIX + 'HermitianCurvatureProofs.OrbitalIntegralConvergesAbs',
    'M146795': MODULE_PREFIX + 'HermitianCurvatureProofs.PhaseFunctionCriticalPoints',
    'M146796': MODULE_PREFIX + 'HermitianCurvatureProofs.PhaseFunctionDerivatives',
    'M146895': MODULE_PREFIX + 'HermitianCurvatureProofs.RemainderNormLeStrictUpper',
    'M147014': MODULE_PREFIX + 'HermitianCurvatureProofs.StabilizerBlockPoint',
    'M147219': MODULE_PREFIX + 'StatementG',
}
CERTIFICATE_PATH = 'port/MeasureSideConditionCertificate.lean'
CERTIFICATE_SHA256 = '814e69a02d3d8447bfcc92f8b860633c8cbbf2f0e044cf9e2a2ebe9bedc517fa'
CASE_PATH = 'port/semantic-review-case.json'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(value, length=64):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(length) + '}', value)


def validate_case(case):
    assert set(case) == {'schema_version', 'case_id', 'source_commit', 'target_ids',
        'required_closure', 'project_manifest', 'pins', 'policy', 'certificate'}
    assert case['schema_version'] == 4 and case['case_id'] == 'M146796'
    assert digest(case['source_commit'], 40), 'Fill the final exact source commit before publication.'
    assert case['target_ids'] == ['M146796']
    assert case['required_closure'] == MODULES
    assert case['pins'] == PINS and case['policy'] == POLICY
    assert case['certificate'] == dict(path=CERTIFICATE_PATH, sha256=CERTIFICATE_SHA256)
    manifest = case['project_manifest']
    assert [row['id'] for row in manifest] == list(MODULES)
    for row in manifest:
        assert set(row) == {'id', 'module', 'original_source_sha256', 'record_sha256',
                            'patch_sha256', 'ported_source_sha256'}
        assert row['module'] == MODULES[row['id']]
        for key in ('original_source_sha256', 'record_sha256', 'ported_source_sha256'):
            assert digest(row[key]), 'Complete every immutable manifest hash.'
        assert row['patch_sha256'] is None or digest(row['patch_sha256'])
        if row['patch_sha256'] is None:
            assert row['ported_source_sha256'] == row['original_source_sha256']
    return case


def prepare():
    env = os.environ
    root = Path(env['GITHUB_WORKSPACE'])
    source, policy, helper = (root / name for name in ('source', 'policy', 'helper'))
    head = lambda directory: subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=directory, text=True).strip()
    helper_commit, source_commit = env['EXPECTED_HELPER_COMMIT'], env['AUDIT_SOURCE_COMMIT']
    assert env['GITHUB_REPOSITORY'] == 'alectionary/alpoge-rh-replay'
    assert digest(helper_commit, 40) and digest(source_commit, 40)
    assert head(helper) == helper_commit == env['GITHUB_SHA']
    case_bytes = (helper / CASE_PATH).read_bytes()
    assert digest(env['EXPECTED_CASE_SHA256'])
    assert sha(case_bytes) == env['EXPECTED_CASE_SHA256']
    case = validate_case(json.loads(case_bytes))
    assert source_commit == case['source_commit'] == head(source)
    assert head(policy) == POLICY['commit'] == env['AUDIT_POLICY_COMMIT']
    for path, key in [('port/islattice_audit.lean', 'audit_script_sha256'),
                      ('port/reused_audit.lean', 'reused_audit_script_sha256')]:
        assert sha((policy / path).read_bytes()) == POLICY[key]
    assert sha((helper / CERTIFICATE_PATH).read_bytes()) == CERTIFICATE_SHA256
    pins = json.loads((source / 'port/target.json').read_bytes())
    assert {key: pins[key] for key in PINS} == PINS
    rows = {row['id']: row for row in map(json.loads,
            gzip.open(source / 'tracker/modules.jsonl.gz', 'rt'))}
    closure, pending = set(), list(case['target_ids'])
    while pending:
        mid = pending.pop()
        if mid not in closure:
            closure.add(mid)
            pending.extend(rows[mid]['imports'])
    assert {mid: rows[mid]['module'] for mid in sorted(closure)} == MODULES
    for item in case['project_manifest']:
        mid, row = item['id'], rows[item['id']]
        record_bytes = (source / 'port/patches' / (mid + '.json')).read_bytes()
        record = json.loads(record_bytes)
        assert record['module'] == row['module'] == item['module']
        assert record['source_sha256'] == row['source_sha256'] == item['original_source_sha256']
        assert record['lean'] == LEAN and record['mathlib'] == MATHLIB
        assert sha(record_bytes) == item['record_sha256']
        patch = source / 'port/patches' / (mid + '.patch')
        assert (sha(patch.read_bytes()) if patch.exists() else None) == item['patch_sha256']
    profile = dict(helper_commit=helper_commit, expected_source_commit=source_commit,
        required_target_ids=case['target_ids'], required_closure=MODULES,
        required_source_manifest=case['project_manifest'], policy_commit=POLICY['commit'],
        audit_script_sha256=POLICY['audit_script_sha256'],
        reused_audit_script_sha256=POLICY['reused_audit_script_sha256'],
        certificate_path=CERTIFICATE_PATH, certificate_sha256=CERTIFICATE_SHA256,
        certified_ported_source_sha256={row['id']: row['ported_source_sha256']
                                       for row in case['project_manifest']},
        lean=LEAN, mathlib=MATHLIB, context_import_mode='reported_module_only',
        case_config_path=CASE_PATH,
        case_config_sha256=sha(case_bytes),
        case_validator_sha256=sha((helper / 'port/semantic_case.py').read_bytes()))
    out = Path(env['RUNNER_TEMP']) / 'semantic-review-v4'
    out.mkdir()
    run_id = int(env['GITHUB_RUN_ID'])
    facts = dict(schema_version=4, source_commit=source_commit, run_id=run_id,
        run_attempt=int(env['GITHUB_RUN_ATTEMPT']),
        run_url='https://github.com/alectionary/alpoge-rh-replay/actions/runs/' + str(run_id),
        workflow_ref=env['GITHUB_WORKFLOW_REF'], target_ids=case['target_ids'],
        profile=profile, project_manifest=case['project_manifest'])
    (out / 'inputs.json').write_text(json.dumps(facts, indent=2) + '\n')
    (out / 'case-config.json').write_bytes(case_bytes)
    with open(env['GITHUB_ENV'], 'a') as exported:
        exported.write('PATCH_IDS=' + ' '.join(case['target_ids']) + '\n')
    for marker, value in [('[AUDIT_SOURCE]', source_commit), ('[AUDIT_HELPER]', helper_commit),
        ('[AUDIT_POLICY]', POLICY['commit']), ('[AUDIT_SCRIPT_SHA256]', POLICY['audit_script_sha256']),
        ('[REUSED_AUDIT_SCRIPT_SHA256]', POLICY['reused_audit_script_sha256']),
        ('[CERTIFICATE_SHA256]', CERTIFICATE_SHA256), ('[CASE_CONFIG_SHA256]', sha(case_bytes)),
        ('[CASE_VALIDATOR_SHA256]', profile['case_validator_sha256'])]:
        print(marker, value, flush=True)
    for item in case['project_manifest']:
        print('[AUDIT_MODULE]', item['id'], item['module'], flush=True)


if __name__ == '__main__':
    prepare()
