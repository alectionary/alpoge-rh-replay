#!/usr/bin/env python3
"""Fork-only bounded source measurement. No invocation dispatches CI or publishes.

Only `run` executes the explicitly bound source, after complete input validation.
The default config is deliberately missing method-review/execution bindings.
"""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import statistics
import subprocess
import time

ORDER = 'ABBAAB'
MANIFEST_SHA256 = 'd2e2b32b6fc0f9e011ed17dd00597f7a1416c5b08407d4cbded09e6dee596c6a'
TARGET = 'Formalism.HermitianCurvature.HermitianCurvatureProofs.PhaseFunctionDerivatives'
ADDITIONAL_PRIVATE_IMPORTS = ()
BASELINE_TARGET_SHA256 = '649fa2f2e244b20dc08ec3cff7adbd4663057adde6ecef89d9f331871139e100'
CANDIDATE_SHA256 = '204428e5edf002dc534323b91594935debb81aacc7e8a2e0f7efdfa202ffb899'
CANDIDATE_PATCH_SHA256 = '8dddb098450c3180690223d667e8757c0b3cdef4387176ea73b4dd5f4b9a506c'
BASELINE = '51d9b1a28026d458aef9c9af3df8b083276e3d2d'
LEAN = 'Lean (version 4.36.0, x86_64-unknown-linux-gnu, commit 611c117bfaf7b7ae1cfcf246ce6fba31e8f509e9, Release)'
LAKE = 'Lake version 5.0.0-src+611c117 (Lean version 4.36.0)'
POSTCHECK_SHA256 = '24a410c93537e4568e94ac98bb527c80386499da7274dda72e7696652c1e3434'
ALLOWED_AXIOMS = {'propext', 'Classical.choice', 'Quot.sound'}
CHECK_DECLARATIONS = {'Formalism.FourierDecayAlt.P.PhaseFunctionDerivatives.b_pow_sub_one',
                      'Formalism.FourierDecayAlt.P.PhaseFunctionDerivatives.b_root_sep'}
COMPILED_SUFFIXES = ('.olean', '.olean.private', '.olean.server', '.ilean', '.ir', '.ir.sig',
                     '.so', '.a', '.o', '.c', '.bc', '.ll')
PINNED_FILES = {
    'lakefile.toml': 'e12dd96eb155851de5107571dbfc959e5d9b230ead90331b4778b55b048590bb',
    'lake-manifest.json': 'ee003c5c7a9b2b2a82a142b6633916661c07117199dd143d94d1af63910237df',
    'lean-toolchain': '582a63f8f9c5128067b688778c1051cf1464c3ca9d57b9325025c051c29b774a',
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


class Budget:
    """Stop the controller by job minute50, leaving10minutes for diagnostics."""
    def __init__(self, started_epoch):
        started_epoch = float(started_epoch)
        require(0 < started_epoch <= time.time() + 1, 'Invalid workflow budget start.')
        self.deadline = time.monotonic() + started_epoch + 3000 - time.time()

    def cap(self, maximum):
        remaining = self.deadline - time.monotonic()
        require(remaining > 0, 'Global job measurement budget exhausted; retain/upload diagnostics.')
        return min(maximum, remaining)


def timeout_for(budget, maximum):
    return budget.cap(maximum) if budget is not None else maximum


def path_checked(path, *, missing=False):
    path = Path(path)
    require('..' not in path.parts, 'Parent path traversal rejected.')
    path = Path(os.path.abspath(path))
    part = Path(path.anchor)
    for name in path.parts[1:]:
        part /= name
        try:
            info = part.lstat()
        except FileNotFoundError:
            require(missing, 'Required path missing: ' + str(part))
            continue
        require(not stat.S_ISLNK(info.st_mode), 'Symlink path rejected: ' + str(part))
    return path


def regular(path):
    path = path_checked(path)
    require(stat.S_ISREG(path.stat().st_mode), 'Expected regular file: ' + str(path))
    return path


def relative_file(root, relative):
    require(isinstance(relative, str) and relative, 'Missing relative input path.')
    rel = PurePosixPath(relative)
    require(not rel.is_absolute() and '..' not in rel.parts and '\\' not in relative, 'Unsafe input path.')
    return regular(Path(root).joinpath(*rel.parts))


def imports(data):
    return [row['module'] for row in import_rows(data)]


def import_rows(data):
    found = []
    for line in data.decode().splitlines():
        match = re.fullmatch(r'(public )?import (all )?([A-Za-z0-9_.]+)', line.strip())
        if match:
            found.append(dict(module=match[3], public=bool(match[1]), all=bool(match[2])))
        else:
            require(re.match(r'^(?:public\s+)?(?:meta\s+)?import\b', line.strip()) is None,
                    'Unsupported import header; do not undercount dependencies.')
    return found


def comparison_graphs(manifest, target, candidate, allowed_additions):
    modules = manifest['modules']
    require(target in modules, 'Target remains unbound or outside the pinned pool.')
    original = modules[target]['import_forms']
    changed = import_rows(candidate)
    require(len({row['module'] for row in changed}) == len(changed), 'Duplicate candidate import.')
    require([row for row in changed if row['public']] == [row for row in original if row['public']], 'Public imports changed.')
    require(all(row in changed for row in original), 'An original import was removed/changed.')
    require(isinstance(allowed_additions, list) and len(allowed_additions) == len(set(allowed_additions)), 'Private import allowance remains unbound.')
    extras = [row for row in changed if row not in original]
    require(extras == [dict(module=name, public=False, all=False) for name in allowed_additions], 'Unreviewed additional import.')
    require(all(name in modules for name in allowed_additions), 'Additional import outside the pinned pool.')
    def closure(candidate_mode):
        seen, pending = set(), [target]
        while pending:
            mid = pending.pop()
            if mid not in seen:
                seen.add(mid)
                dependencies = ([row['module'] for row in changed if row['module'] in modules]
                                if candidate_mode and mid == target else modules[mid]['project_imports'])
                pending.extend(dependencies)
        return seen
    baseline, selected = closure(False), closure(True)
    # Reject an added private dependency which would import its new owner back.
    for added in allowed_additions:
        seen, pending = set(), [added]
        while pending:
            mid = pending.pop()
            require(mid != target, 'Candidate import creates a cycle.')
            if mid not in seen:
                seen.add(mid)
                pending.extend(modules[mid]['project_imports'])
    return dict(baseline=sorted(baseline), candidate=sorted(selected), union=sorted(baseline | selected),
                baseline_direct_imports=original, candidate_direct_imports=changed,
                baseline_project_dependencies=len(baseline) - 1, candidate_project_dependencies=len(selected) - 1)


def load_config(path, expected_sha):
    """Validate every binding before any network call, subprocess or output write."""
    path = regular(path)
    raw = path.read_bytes()
    require(sha(expected_sha) and digest(raw) == expected_sha, 'Config digest does not match.')
    config = json.loads(raw)
    require(config['schema_version'] == 1 and config['comparison_mode'] == 'baseline_closure_plus_target_patch', 'Unknown comparison mode.')
    require(config['baseline'] == {'repository': 'leanprover-community/riemann-hypothesis', 'commit': BASELINE}, 'Wrong immutable baseline.')
    require(config['target_module'] == TARGET and config['order'] == ORDER, 'Target remains unbound or wrong order.')
    require(isinstance(config['execution_repository'], str) and re.fullmatch(r'alectionary/[A-Za-z0-9_.-]+', config['execution_repository']), 'Execution fork remains unbound.')
    for name, value in config['required_reviews'].items():
        require(sha(value), 'Required review remains unbound: ' + name)
    require(set(config['required_reviews']) == {'root_candidate', 'independent_candidate', 'root_method', 'independent_method'}, 'Review bindings incomplete.')
    manifest_bytes = relative_file(path.parent, config['manifest']['path']).read_bytes()
    require(config['manifest']['sha256'] == MANIFEST_SHA256 and digest(manifest_bytes) == MANIFEST_SHA256, 'Manifest digest differs.')
    manifest = json.loads(manifest_bytes)
    require(manifest['source_commit'] == BASELINE and manifest['target'] == TARGET and len(manifest['modules']) == 11, 'Wrong source closure.')
    require(manifest['config_files'] == PINNED_FILES, 'Canonical config pins differ.')
    modules = manifest['modules']
    require(all(row['path'] == 'src/' + mid.replace('.', '/') + '.lean' and sha(row['sha256']) for mid, row in modules.items()), 'Invalid module manifest.')
    require(all(dep in modules for row in modules.values() for dep in row['project_imports']), 'Incomplete project closure.')
    seen, pending = set(), [TARGET]
    while pending:
        mid = pending.pop()
        if mid not in seen:
            seen.add(mid)
            pending.extend(modules[mid]['project_imports'])
    require(seen == set(modules) and len(seen) == 11, 'Baseline closure differs.')
    require(modules[TARGET]['sha256'] == BASELINE_TARGET_SHA256, 'Wrong zero-import root-separation baseline source.')
    candidate = config['candidate']
    require(candidate['source_sha256'] == CANDIDATE_SHA256 and candidate['patch_sha256'] == CANDIDATE_PATCH_SHA256, 'Candidate remains unbound or differs from this fixed zero-import root-separation prototype.')
    data = relative_file(path.parent, candidate['source_path']).read_bytes()
    patch = relative_file(path.parent, candidate['patch_path']).read_bytes()
    require(digest(data) == candidate['source_sha256'] and digest(patch) == candidate['patch_sha256'], 'Candidate/patch bytes differ.')
    require(candidate['additional_private_imports'] == list(ADDITIONAL_PRIVATE_IMPORTS), 'Private import allowance remains unbound or differs.')
    graphs = comparison_graphs(manifest, config['target_module'], data, candidate['additional_private_imports'])
    require(set(graphs['union']) == set(modules) and graphs['baseline'] == graphs['candidate'] and len(graphs['candidate']) == 11, 'Candidate union differs.')
    driver = relative_file(path.parent, config['post_build_driver']['path']).read_bytes()
    require(config['post_build_driver']['sha256'] == POSTCHECK_SHA256 and digest(driver) == POSTCHECK_SHA256, 'Post-build driver differs.')
    return config, manifest, data, patch, raw


def clean_environment(workspace):
    env = {key: os.environ[key] for key in ('PATH', 'HOME', 'ELAN_HOME', 'SSL_CERT_FILE', 'SSL_CERT_DIR') if key in os.environ}
    env.update(LC_ALL='C', LANG='C', ELAN_TOOLCHAIN='leanprover/lean4:v4.36.0',
               LEAN_ABORT_ON_PANIC='1', LEAN_NUM_THREADS='2', LAKE_ARTIFACT_CACHE='false',
               LAKE_RESTORE_ARTIFACTS='false', LAKE_NO_CACHE='true',
               LAKE_CACHE_DIR=str(workspace / '.isolated-lake-cache'),
               MATHLIB_CACHE_GET_URL='https://cache.mathlib.org/mathlib4')
    return env


def fetch_input(config, relative, wanted, env, budget, log_path):
    url = 'https://raw.githubusercontent.com/' + config['baseline']['repository'] + '/' + BASELINE + '/' + relative
    maximum = timeout_for(budget, 120)
    command = ['curl', '--fail', '--location', '--silent', '--show-error', '--max-time', str(maximum),
               '--max-filesize', '2097152', url]
    result = subprocess.run(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            check=False, timeout=maximum)
    with log_path.open('ab') as log:
        log.write(encode(dict(command=command, exit_code=result.returncode, stderr=result.stderr.decode(errors='replace'))))
    require(result.returncode == 0, 'Input HTTP request failed.')
    data = result.stdout
    require(len(data) <= 2 * 1024 * 1024 and digest(data) == wanted, 'Fetched input digest differs: ' + relative)
    return data


def input_seal(workspace, expected):
    for relative, wanted in expected.items():
        require(digest(relative_file(workspace, relative).read_bytes()) == wanted, 'Input changed: ' + relative)


def artifact_roots(workspace):
    roots = [workspace / '.lake/build/lib/lean', workspace / '.lake/build/ir']
    packages = workspace / '.lake/packages'
    if packages.is_dir():
        for package in sorted(packages.iterdir()):
            require(not package.is_symlink(), 'Dependency symlink rejected.')
            roots += [package / '.lake/build/lib/lean', package / '.lake/build/ir']
    return roots


def target_bases(workspace, target=TARGET):
    module = Path(*target.split('.'))
    return [workspace / '.lake/build' / sub / module for sub in ('lib/lean', 'ir')]


def target_files(workspace, target=TARGET):
    found = []
    for base in target_bases(workspace, target):
        path_checked(base.parent, missing=True)
        if not base.parent.exists():
            continue
        for item in base.parent.iterdir():
            if item.name.startswith(base.name + '.'):
                require(not item.is_symlink() and item.is_file(), 'Nonregular target artifact rejected.')
                found.append(regular(item))
    return sorted(found)


def clean_target(workspace, target=TARGET):
    removed = []
    for path in target_files(workspace, target):
        removed.append(str(path.relative_to(workspace)))
        path.unlink()
    require(not target_files(workspace, target), 'Target artifact cleanup incomplete.')
    return removed


def artifact_rows(workspace, *, exclude_target=False, target=TARGET, budget=None):
    excluded = set(target_files(workspace, target)) if exclude_target else set()
    rows = {}
    for root in artifact_roots(workspace):
        path_checked(root, missing=True)
        if root.exists():
            for path in sorted(root.rglob('*')):
                if budget is not None:
                    budget.cap(1)
                require(not path.is_symlink(), 'Artifact symlink rejected.')
                if path.is_dir() or path in excluded:
                    continue
                path = regular(path)
                # Rehash may refresh bookkeeping without recompiling imports.
                # Seal real compiled inputs, not .hash/.trace/setup/LTAR state.
                if not path.name.endswith(COMPILED_SUFFIXES):
                    continue
                info = path.stat()
                rows[str(path.relative_to(workspace))] = dict(bytes=info.st_size, sha256=digest(path.read_bytes()), mtime_ns=info.st_mtime_ns)
    return rows


def package_identity(workspace, env, budget=None):
    manifest = json.loads((workspace / 'lake-manifest.json').read_bytes())
    rows = {}
    for item in manifest['packages']:
        require(item['type'] == 'git' and not item.get('subDir'), 'Unsupported dependency kind.')
        package = path_checked(workspace / '.lake/packages' / item['name'])
        def git(*args):
            return subprocess.check_output(['git', '-C', str(package), *args], env=env, text=True,
                                           timeout=timeout_for(budget, 60)).strip()
        require(git('rev-parse', 'HEAD') == item['rev'], 'Dependency commit differs: ' + item['name'])
        require(not git('status', '--porcelain', '--untracked-files=no'), 'Tracked dependency changes: ' + item['name'])
        require(not git('ls-files', '--others', '--exclude-standard', '--', '*.lean', 'lakefile.toml', 'lake-manifest.json', 'lean-toolchain'), 'Untracked dependency code: ' + item['name'])
        rows[item['name']] = item['rev']
    require(rows['mathlib'] == 'fc4f59e577feb1a4956671bc04ac18aaaf8cd842', 'Mathlib pin differs.')
    return rows


def sandbox_prefix(workspace):
    return ['bwrap', '--die-with-parent', '--new-session', '--unshare-user', '--unshare-pid',
            '--unshare-ipc', '--unshare-net', '--unshare-uts', '--ro-bind', '/', '/',
            '--bind', str(workspace), str(workspace),
            '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--chdir', str(workspace), '--']


def sandbox_command(workspace, targets):
    return sandbox_prefix(workspace) + ['lake', '--rehash', 'build'] + ['+' + target for target in targets]


def time_metrics(data):
    text = data.decode()
    rss = re.findall(r'^\s*Maximum resident set size \(kbytes\): (\d+)$', text, re.M)
    exit_codes = re.findall(r'^\s*Exit status: (\d+)$', text, re.M)
    elapsed = re.findall(r'^\s*Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): (.+)$', text, re.M)
    require(len(rss) == len(exit_codes) == len(elapsed) == 1, 'Incomplete GNU time output.')
    return dict(gnu_max_rss_kbytes=int(rss[0]), gnu_exit_status=int(exit_codes[0]), gnu_elapsed_text=elapsed[0],
                rss_scope='GNU time reported command/process-family maximum; not total concurrent RAM')


def sandbox_preflight(workspace, output, env, toolchain_bin, budget=None):
    output.mkdir()
    records = {}
    for name, expected in (('lean', LEAN), ('lake', LAKE)):
        command = sandbox_prefix(workspace) + [str(toolchain_bin / name), '--version']
        with (output / (name + '.stdout.log')).open('wb') as stdout, (output / (name + '.stderr.log')).open('wb') as stderr:
            process = subprocess.run(command, cwd=workspace, env=env, stdout=stdout, stderr=stderr, check=False, timeout=timeout_for(budget, 30))
        record = dict(command=command, exit_code=process.returncode,
                      stdout_sha256=digest((output / (name + '.stdout.log')).read_bytes()),
                      stderr_sha256=digest((output / (name + '.stderr.log')).read_bytes()))
        records[name] = record
        (output / 'result.json').write_bytes(encode(records))
        require(process.returncode == 0 and (output / (name + '.stdout.log')).read_text().strip() == expected,
                'Noncompiling sandbox/toolchain probe failed; see retained diagnostics.')
    return records


def trial(workspace, output, label, expected, dependencies, env, *, target=TARGET, budget=None, executor=subprocess.run):
    output.mkdir(parents=True, exist_ok=False)
    removed = clean_target(workspace, target)
    input_seal(workspace, expected)
    require(artifact_rows(workspace, exclude_target=True, target=target, budget=budget) == dependencies, 'Imported artifacts changed before trial.')
    olean = Path(str(target_bases(workspace, target)[0]) + '.olean')
    require(not olean.exists() and not olean.is_symlink(), 'Target olean exists before build.')
    command = ['/usr/bin/time', '-v', '-o', str(output / 'time-v.txt'), '--'] + sandbox_command(workspace, [target])
    result = dict(label=label, status='started', command=command, environment=env,
                  removed_target_artifacts=removed, publication_approved=False, full_proof_verified=False)
    started = time.monotonic()
    started_ns = time.time_ns()
    try:
        with (output / 'build.log').open('wb') as log:
            process = executor(command, cwd=workspace, env=env, stdout=log, stderr=subprocess.STDOUT, check=False, timeout=timeout_for(budget, 300))
        result.update(exit_code=process.returncode, monotonic_wall_seconds=time.monotonic() - started)
        if (output / 'time-v.txt').exists():
            result.update(time_metrics((output / 'time-v.txt').read_bytes()))
        require(process.returncode == 0, 'Actual module command failed.')
        require(result.get('gnu_exit_status') == 0, 'GNU time status is missing/nonzero.')
        info = regular(olean).stat()
        require(info.st_size > 0 and info.st_mtime_ns >= started_ns, 'No fresh nonempty target olean emitted.')
        input_seal(workspace, expected)
        require(artifact_rows(workspace, exclude_target=True, target=target, budget=budget) == dependencies, 'Imported artifacts changed during trial.')
        artifacts = {str(path.relative_to(workspace)): dict(bytes=path.stat().st_size, sha256=digest(path.read_bytes())) for path in target_files(workspace, target)}
        require(all(any(name.endswith(suffix) for name in artifacts) for suffix in ('.olean', '.olean.private', '.olean.server')), 'Current module olean family is incomplete.')
        result.update(status='passed', target_artifacts=artifacts,
                      olean_family_bytes=sum(row['bytes'] for name, row in artifacts.items() if name.endswith(('.olean', '.olean.private', '.olean.server'))),
                      all_target_lean_artifact_bytes=sum(row['bytes'] for name, row in artifacts.items() if '/lib/lean/' in name),
                      all_target_artifact_bytes=sum(row['bytes'] for row in artifacts.values()))
    except Exception as error:
        result.update(status='failed', error_type=type(error).__name__, error=str(error), monotonic_wall_seconds=time.monotonic() - started)
        raise
    finally:
        result['retained_logs'] = {name: dict(sha256=digest((output / name).read_bytes()), bytes=(output / name).stat().st_size)
                                   for name in ('build.log', 'time-v.txt') if (output / name).is_file()}
        (output / 'result.json').write_bytes(encode(result))
    return result


def summarize(rows):
    require([row['label'] for row in rows] == list(ORDER) and all(row['status'] == 'passed' for row in rows), 'Incomplete/failed comparison; no timing summary.')
    groups = {label: [row['monotonic_wall_seconds'] for row in rows if row['label'] == label] for label in 'AB'}
    require(all(value > 0 for group in groups.values() for value in group), 'Invalid measured duration.')
    pairs = []
    for index in range(0, 6, 2):
        pair = {row['label']: row for row in rows[index:index + 2]}
        pairs.append(dict(A_seconds=pair['A']['monotonic_wall_seconds'], B_seconds=pair['B']['monotonic_wall_seconds'],
                          observed_A_over_B=pair['A']['monotonic_wall_seconds'] / pair['B']['monotonic_wall_seconds']))
    return dict(order=ORDER, per_variant_seconds=groups, paired_results=pairs,
                median_A_seconds=statistics.median(groups['A']), median_B_seconds=statistics.median(groups['B']),
                observed_median_A_over_B=statistics.median(groups['A']) / statistics.median(groups['B']),
                interpretation='Preliminary bounded-module measurements only; no full-proof or reproducible-speedup claim.',
                publication_approved=False, full_proof_verified=False)


def parse_axioms(stdout):
    records, block, completed = {}, [], False
    for line in stdout.splitlines():
        if not line.strip() and not block:
            continue
        if line == '[BENCH_POSTCHECK_COMPLETED]':
            require(not completed and not block, 'Malformed/duplicate post-check completion.')
            completed = True
            continue
        require(not completed, 'Output follows post-check completion.')
        if not block:
            require(line.startswith('[BENCH_AXIOMS] '), 'Unexpected post-check output.')
        block.append(line)
        if ']' not in line.split(':', 1)[-1]:
            continue
        match = re.fullmatch(r'\[BENCH_AXIOMS\] ([A-Za-z0-9_.]+):\s*\[\s*([A-Za-z0-9_.,\s]*)\]', '\n'.join(block))
        require(match is not None, 'Malformed axiom record.')
        name, terms = match.groups()
        axioms = [term.strip() for term in terms.split(',')] if terms.strip() else []
        require(name in CHECK_DECLARATIONS and name not in records, 'Unowned/duplicate post-check declaration.')
        require(all(axioms) and len(set(axioms)) == len(axioms) and set(axioms) <= ALLOWED_AXIOMS, 'Unexpected post-check axiom.')
        records[name] = sorted(axioms)
        block = []
    require(completed and not block and set(records) == CHECK_DECLARATIONS, 'Incomplete post-check inventory.')
    return records


def post_check(workspace, output, driver, expected, dependencies, env, target, budget=None):
    output.mkdir()
    (workspace / 'BenchmarkPostCheck.lean').write_bytes(driver)
    (output / 'driver.lean').write_bytes(driver)
    command = sandbox_prefix(workspace) + ['lake', 'env', 'lean', 'BenchmarkPostCheck.lean']
    before = {str(path): (digest(path.read_bytes()), path.stat().st_mtime_ns) for path in target_files(workspace, target)}
    result = dict(command=command, driver_sha256=digest(driver), status='started', timing_scope='Outside measured module build')
    try:
        with (output / 'stdout.log').open('wb') as stdout, (output / 'stderr.log').open('wb') as stderr:
            process = subprocess.run(command, cwd=workspace, env=env, stdout=stdout, stderr=stderr, check=False, timeout=timeout_for(budget, 120))
        result['exit_code'] = process.returncode
        require(process.returncode == 0, 'Exact-type/axiom driver failed.')
        require('sorryAx' not in (output / 'stderr.log').read_text(), 'Admission in post-check diagnostics.')
        result['axioms'] = parse_axioms((output / 'stdout.log').read_text())
        input_seal(workspace, expected)
        require(artifact_rows(workspace, exclude_target=True, target=target, budget=budget) == dependencies, 'Post-check mutated dependencies.')
        require(before == {str(path): (digest(path.read_bytes()), path.stat().st_mtime_ns) for path in target_files(workspace, target)}, 'Post-check mutated target artifacts.')
        result['status'] = 'passed'
    except Exception as error:
        result.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        result['files'] = {name: dict(sha256=digest((output / name).read_bytes()), bytes=(output / name).stat().st_size)
                           for name in ('driver.lean', 'stdout.log', 'stderr.log') if (output / name).is_file()}
        (output / 'result.json').write_bytes(encode(result))
    return result


def run(config_path, config_sha, workspace, output):
    config, manifest, candidate, patch, raw_config = load_config(config_path, config_sha)
    require(os.environ.get('GITHUB_REPOSITORY') == config['execution_repository'], 'Wrong execution repository.')
    require(os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch', 'Manual dispatch is required.')
    require(re.fullmatch('[0-9a-f]{40}', os.environ.get('EXPECTED_HELPER_COMMIT', '')) is not None and
            os.environ.get('GITHUB_SHA') == os.environ['EXPECTED_HELPER_COMMIT'], 'Helper identity differs.')
    budget = Budget(os.environ.get('BENCH_JOB_START_EPOCH', '0'))
    budget.cap(1)
    workspace, output = path_checked(workspace, missing=True), path_checked(output, missing=True)
    require(not workspace.is_relative_to(output) and not output.is_relative_to(workspace), 'Workspace and controller evidence paths must be disjoint.')
    require(not workspace.exists() and not output.exists(), 'Fresh workspace/output paths required; retain previous failed attempts.')
    workspace.mkdir(parents=True)
    output.mkdir(parents=True)
    (output / 'config.json').write_bytes(raw_config)
    (output / 'source-manifest.json').write_bytes(encode(manifest))
    (output / 'candidate.lean').write_bytes(candidate)
    (output / 'candidate.patch').write_bytes(patch)
    driver = relative_file(config_path.parent, config['post_build_driver']['path']).read_bytes()
    receipt = dict(schema_version=1, comparison_mode=config['comparison_mode'], status='preparing',
                   config_sha256=config_sha, harness_sha256=digest(Path(__file__).read_bytes()),
                   expected_helper_commit=os.environ['EXPECTED_HELPER_COMMIT'],
                   workflow_budget_start_epoch=os.environ['BENCH_JOB_START_EPOCH'], controller_deadline_minutes=50,
                   github={key: os.environ.get(key) for key in ('GITHUB_REPOSITORY', 'GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_WORKFLOW_REF')},
                   publication_approved=False, full_proof_verified=False)
    try:
        env = clean_environment(workspace)
        expected = dict(PINNED_FILES)
        expected.update({row['path']: row['sha256'] for row in manifest['modules'].values()})
        for relative, wanted in expected.items():
            data = fetch_input(config, relative, wanted, env, budget, output / 'fetch-inputs.log')
            path = workspace / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            retained = output / 'baseline-inputs' / relative
            retained.parent.mkdir(parents=True, exist_ok=True)
            retained.write_bytes(data)
        receipt['actual_input_sha256'] = dict(expected)
        target = config['target_module']
        graphs = comparison_graphs(manifest, target, candidate, config['candidate']['additional_private_imports'])
        receipt['source_graphs'] = graphs
        target_path = manifest['modules'][target]['path']
        original = (workspace / target_path).read_bytes()
        canonical_patch = ''.join(difflib.unified_diff(original.decode().splitlines(True), candidate.decode().splitlines(True),
                                                     fromfile='a/' + target_path, tofile='b/' + target_path)).encode()
        require(canonical_patch == patch, 'Candidate patch does not exactly describe the target overlay.')
        (workspace / '.isolated-lake-cache').mkdir()
        actual_lean = regular(subprocess.check_output(['elan', 'which', 'lean'], env=env, text=True, timeout=timeout_for(budget, 30)).strip())
        actual_lake = regular(subprocess.check_output(['elan', 'which', 'lake'], env=env, text=True, timeout=timeout_for(budget, 30)).strip())
        require(actual_lake.parent == actual_lean.parent, 'Stock Lean/Lake installations differ.')
        toolchain_bin = path_checked(actual_lean.parent)
        receipt['stock_binary_sha256'] = {name: digest((toolchain_bin / name).read_bytes()) for name in ('lean', 'lake')}
        env['PATH'] = str(toolchain_bin) + os.pathsep + env['PATH']
        receipt['stock_toolchain_bin'] = str(toolchain_bin)
        receipt['environment'] = env
        receipt['host'] = dict(uname=list(os.uname()), cpu_count=os.cpu_count(), available_disk_bytes=os.statvfs(workspace).f_bavail * os.statvfs(workspace).f_frsize,
                               proc_meminfo=Path('/proc/meminfo').read_text())
        versions = {name: subprocess.check_output([str(toolchain_bin / name), '--version'], env=env, text=True, timeout=timeout_for(budget, 30)).strip() for name in ('lean', 'lake')}
        require(versions == {'lean': LEAN, 'lake': LAKE}, 'Actual compiler/Lake identity differs.')
        receipt['versions'] = versions
        receipt['sandbox_preflight'] = sandbox_preflight(workspace, output / 'sandbox-preflight', env, toolchain_bin, budget)
        cache_command = ['lake', 'exe', 'mathlib/cache', 'get']
        receipt['mathlib_setup_command'] = cache_command
        with (output / 'mathlib-setup.log').open('wb') as log:
            setup = subprocess.run(cache_command, cwd=workspace, env=env, stdout=log, stderr=subprocess.STDOUT, check=False, timeout=timeout_for(budget, 900))
        receipt['mathlib_setup_exit_code'] = setup.returncode
        require(setup.returncode == 0, 'Official Mathlib cache setup failed.')
        packages = package_identity(workspace, env, budget)
        input_seal(workspace, expected)
        # The one baseline warm-up builds the unchanged exact fifteen-source union; no import is added.
        warm_dir = output / 'warm-baseline'
        # Warm-up legitimately creates project imports, so only its execution/log
        # retention is shared with measured trials; imported seals start afterward.
        warm_dir.mkdir()
        warm_command = ['/usr/bin/time', '-v', '-o', str(warm_dir / 'time-v.txt'), '--'] + sandbox_command(workspace, graphs['union'])
        receipt['cold_baseline_warm_command'] = warm_command
        warm_started = time.monotonic()
        try:
            with (warm_dir / 'build.log').open('wb') as log:
                warm = subprocess.run(warm_command, cwd=workspace, env=env, stdout=log, stderr=subprocess.STDOUT, check=False, timeout=timeout_for(budget, 900))
        finally:
            receipt['cold_baseline_warm_wall_seconds'] = time.monotonic() - warm_started
        receipt['cold_baseline_warm_exit_code'] = warm.returncode
        if (warm_dir / 'time-v.txt').is_file():
            receipt['cold_baseline_warm_metrics'] = time_metrics((warm_dir / 'time-v.txt').read_bytes())
        require(warm.returncode == 0, 'Actual cold baseline build failed; logs retained.')
        require(package_identity(workspace, env, budget) == packages, 'Package identity changed in warm-up.')
        input_seal(workspace, expected)
        for mid in graphs['union']:
            path = workspace / '.lake/build/lib/lean' / Path(*mid.split('.')).with_suffix('.olean')
            require(regular(path).stat().st_size > 0, 'Warm closure module missing: ' + mid)
        dependencies = artifact_rows(workspace, exclude_target=True, target=target, budget=budget)
        (output / 'dependency-artifacts.json').write_bytes(encode(dependencies))
        receipt.update(package_heads=packages, dependency_artifacts_sha256=digest(encode(dependencies)),
                       available_dependency_olean_files=sum(name.endswith('.olean') for name in dependencies),
                       source_import_counts=dict(baseline_direct=len(graphs['baseline_direct_imports']),
                                                 candidate_direct=len(graphs['candidate_direct_imports']),
                                                 baseline_project_dependencies=graphs['baseline_project_dependencies'],
                                                 candidate_project_dependencies=graphs['candidate_project_dependencies'],
                                                 warmed_project_modules=len(graphs['union']),
                                                 external_source_imports=sorted({name for mid in graphs['union'] for name in manifest['modules'][mid]['other_imports']})),
                       import_count_scope='Measured from unchanged source graph; cached-olean inventory is not an actual imported-module count.')
        rows = []
        expected_axioms = None
        for index, label in enumerate(ORDER):
            data = original if label == 'A' else candidate
            (workspace / target_path).write_bytes(data)
            current = dict(expected, **{target_path: digest(data)})
            require(package_identity(workspace, env, budget) == packages, 'Package identity changed before trial.')
            row = trial(workspace, output / f'trial-{index + 1}-{label}', label, current, dependencies, env, target=target, budget=budget)
            checked = post_check(workspace, output / f'trial-{index + 1}-{label}' / 'post-check', driver,
                                 current, dependencies, env, target, budget)
            if expected_axioms is None:
                expected_axioms = checked['axioms']
            require(checked['axioms'] == expected_axioms, 'Baseline/candidate theorem axiom inventories differ.')
            row['post_check_axioms'] = checked['axioms']
            require(package_identity(workspace, env, budget) == packages, 'Package identity changed after trial.')
            rows.append(row)
        receipt.update(status='completed', trials=[row['label'] for row in rows],
                       post_check_axiom_inventory=expected_axioms, summary=summarize(rows))
        (output / 'summary.json').write_bytes(encode(receipt['summary']))
    except Exception as error:
        receipt.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        receipt['files_sha256'] = {str(path.relative_to(output)): digest(path.read_bytes()) for path in sorted(output.rglob('*')) if path.is_file() and path.name != 'receipt.json'}
        (output / 'receipt.json').write_bytes(encode(receipt))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('validate', 'run'))
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--config-sha256', required=True)
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    load_config(args.config, args.config_sha256)
    if args.mode == 'run':
        require(args.workspace is not None and args.output is not None, 'Run paths missing.')
        run(args.config, args.config_sha256, args.workspace, args.output)
    else:
        print('Bound input shapes and hashes validated; no build or mathematical approval.')


if __name__ == '__main__':
    main()
