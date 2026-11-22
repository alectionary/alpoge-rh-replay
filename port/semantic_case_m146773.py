"""Private, case-specific immutable input validation for the M146773 producer proposal.

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
TARGET_ID = 'M146773'
REFERENCE_MAIN = '65c11a5133da65c6f0a077aba2c0a0d8749506fd'
MODULES = {'M144279': 'Formalism.DoubleCosetMeasures.LowerUnipotentOrbits.LowUniMulVecELast',
 'M144281': 'Formalism.DoubleCosetMeasures.LowerUnipotentOrbits.MulInvBlockDiagApplySameBlock',
 'M144284': 'Formalism.DoubleCosetMeasures.Statement',
 'M145337': 'Formalism.HermitianCurvature.BlockKernelPropertiesOfSteps',
 'M146475': 'Formalism.HermitianCurvature.HermitianCurvatureProofs.IntegralLatticeRefinementIdentity',
 'M146511': 'Formalism.HermitianCurvature.HermitianCurvatureProofs.KernelNonzeroModulusDeterminantEq',
 'M146773': 'Formalism.HermitianCurvature.HermitianCurvatureProofs.PadicChangeOfVariables',
 'M147251': 'Formalism.HermitianCurvature.ThetaExistenceInductiveFromPieces'}
ORIGINALS = {'M144279': 'c8564979f9926720de0079de4559848c5fb1ecc031322069073409337d3f23d8',
 'M144281': '52236547bf222b6f971ed9d386bdf410467cfe7f954479b5494368fbaf7a47ad',
 'M144284': '02eab37f3d4d4ba211fc3ff70c478ecff9d86e9ecb996209b29be2e4d7be488a',
 'M145337': 'b91f98f2740e656a565a9d0946c6033e23c15676b1fc8920b7e20eddb28acb47',
 'M146475': '1f62a75214447e8ac1ed271c2e35ca510b3ed126197dac99a17651f659b90e6e',
 'M146511': 'e5dbe8de5d6cfb92b78bb97e3ee04a4a9a12800fe51580092fd15a62e1287f92',
 'M146773': '976d0973136b796c8d11d84287241002307292bc9f6f21d08753bd67525cced1',
 'M147251': '774ed1c6403ef49ab1fc05cc392db51e0ea330f49f0a91af8895711ff462bbac'}
REFERENCE_IMPORTS = {'M144279': {'id': 'M144279',
             'module': 'Formalism.DoubleCosetMeasures.LowerUnipotentOrbits.LowUniMulVecELast',
             'original_source_sha256': 'c8564979f9926720de0079de4559848c5fb1ecc031322069073409337d3f23d8',
             'patch_sha256': None,
             'ported_source_sha256': 'c8564979f9926720de0079de4559848c5fb1ecc031322069073409337d3f23d8',
             'record_sha256': '5508e7bc3288fd48777efda490f8045156627cb6a6a52f28c588cfbb9337ccbf'},
 'M144281': {'id': 'M144281',
             'module': 'Formalism.DoubleCosetMeasures.LowerUnipotentOrbits.MulInvBlockDiagApplySameBlock',
             'original_source_sha256': '52236547bf222b6f971ed9d386bdf410467cfe7f954479b5494368fbaf7a47ad',
             'patch_sha256': None,
             'ported_source_sha256': '52236547bf222b6f971ed9d386bdf410467cfe7f954479b5494368fbaf7a47ad',
             'record_sha256': '5f4eccec1cf70621931d3fdad54207109d86909fb63d9103eb57890a7e214f87'},
 'M144284': {'id': 'M144284',
             'module': 'Formalism.DoubleCosetMeasures.Statement',
             'original_source_sha256': '02eab37f3d4d4ba211fc3ff70c478ecff9d86e9ecb996209b29be2e4d7be488a',
             'patch_sha256': '13b1c391c06e4a86e0a9e0fc3b19fea92b4bb34c300e7ff475667a0415051b26',
             'ported_source_sha256': 'f232870a0bb149de3d9bfa9dace5626e1ce10374e903e501a499475692800f21',
             'record_sha256': '77725a7debd94b018ce11736b888266a9a4b7f3d78044d292b9701bf10c2a780'},
 'M145337': {'id': 'M145337',
             'module': 'Formalism.HermitianCurvature.BlockKernelPropertiesOfSteps',
             'original_source_sha256': 'b91f98f2740e656a565a9d0946c6033e23c15676b1fc8920b7e20eddb28acb47',
             'patch_sha256': None,
             'ported_source_sha256': 'b91f98f2740e656a565a9d0946c6033e23c15676b1fc8920b7e20eddb28acb47',
             'record_sha256': '408f5e41a59915f259f77d796e88b417c288b9d689b98627c376a08500fa2619'},
 'M146475': {'id': 'M146475',
             'module': 'Formalism.HermitianCurvature.HermitianCurvatureProofs.IntegralLatticeRefinementIdentity',
             'original_source_sha256': '1f62a75214447e8ac1ed271c2e35ca510b3ed126197dac99a17651f659b90e6e',
             'patch_sha256': None,
             'ported_source_sha256': '1f62a75214447e8ac1ed271c2e35ca510b3ed126197dac99a17651f659b90e6e',
             'record_sha256': 'bbec827531928ab39f0e02e6e4d5cda4bae68cc6cc38e4322d66fb1d4301f187'},
 'M146511': {'id': 'M146511',
             'module': 'Formalism.HermitianCurvature.HermitianCurvatureProofs.KernelNonzeroModulusDeterminantEq',
             'original_source_sha256': 'e5dbe8de5d6cfb92b78bb97e3ee04a4a9a12800fe51580092fd15a62e1287f92',
             'patch_sha256': '08da2213a1a73e0d47dc58e2602c35108bc6807666c35d92d7835d5f21f47578',
             'ported_source_sha256': '12b0e49890de2e4b191688a4c6fda75565cc4bf2ad00cc52046c0784372ef961',
             'record_sha256': '66060c4b593e8c51388f69f7ccf6cec5ec7ee9bb9666e214764942493fff8d03'},
 'M147251': {'id': 'M147251',
             'module': 'Formalism.HermitianCurvature.ThetaExistenceInductiveFromPieces',
             'original_source_sha256': '774ed1c6403ef49ab1fc05cc392db51e0ea330f49f0a91af8895711ff462bbac',
             'patch_sha256': None,
             'ported_source_sha256': '774ed1c6403ef49ab1fc05cc392db51e0ea330f49f0a91af8895711ff462bbac',
             'record_sha256': 'b3709e5080255b71a70c3f6167abcdbf2dd46249dd7208e6051b1a028c64d925'}}
CERTIFICATE_PATH = 'port/GuardedProductCertificate.lean'
CERTIFICATE_SHA256 = '8eb205e139a091957c09ab0fa7bf05e3a7f9703d4d9d36b84c9a59c054080d18'
CASE_PATH = 'port/semantic-review-m146773-case.json'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(value, length=64):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(length) + '}', value)


def validate_manifest_row(row):
    """Validate known originals/current import bindings; the future target stays dynamic."""
    assert set(row) == {'id', 'module', 'original_source_sha256', 'record_sha256',
                        'patch_sha256', 'ported_source_sha256'}
    mid = row['id']
    assert mid in MODULES and row['module'] == MODULES[mid]
    assert row['original_source_sha256'] == ORIGINALS[mid]
    for key in ('record_sha256', 'ported_source_sha256'):
        assert digest(row[key]), 'The actual exact source must supply every hash.'
    assert row['patch_sha256'] is None or digest(row['patch_sha256'])
    if row['patch_sha256'] is None:
        assert row['ported_source_sha256'] == row['original_source_sha256']
    if mid != TARGET_ID:
        assert row == REFERENCE_IMPORTS[mid], 'Accepted import changed; independently review a new proposal.'
    return row


def validate_case(case):
    assert set(case) == {'schema_version', 'case_id', 'source_commit', 'target_ids',
        'required_closure', 'project_manifest', 'pins', 'policy', 'certificate'}
    assert case['schema_version'] == 4 and case['case_id'] == TARGET_ID
    assert digest(case['source_commit'], 40), 'Wait for the actual final exact source commit.'
    assert case['target_ids'] == [TARGET_ID]
    assert case['required_closure'] == MODULES
    assert case['pins'] == PINS and case['policy'] == POLICY
    assert case['certificate'] == dict(path=CERTIFICATE_PATH, sha256=CERTIFICATE_SHA256)
    manifest = case['project_manifest']
    assert [row['id'] for row in manifest] == list(MODULES)
    for row in manifest:
        validate_manifest_row(row)
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
        case_validator_sha256=sha((helper / 'port/semantic_case_m146773.py').read_bytes()))
    out = Path(env['RUNNER_TEMP']) / 'semantic-review-m146773'
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
