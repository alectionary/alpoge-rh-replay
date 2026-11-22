#!/usr/bin/env python3
"""Fork-only, baseline-only attribution diagnostic; no dispatch or publication."""
import argparse
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import stat
import subprocess
import sys
import time

sys.dont_write_bytecode = True
BASE = '291b7446ece6917c5cd959edd98510fdc06947b2'
TARGET = 'Formalism.HermitianCurvature.HermitianCurvatureProofs.EtaleIntegralityFacts'
CORE_SHA = '20fa8da717588e2e07c1bd8a1a9fc58a8ba40fa57dfe81667aeb6732dcf12f9c'
MANIFEST_SHA = '42bce92d6ff48d8756d421979c17fab82f4eb106d461fa42af53b7a67c361fd8'
DRIVER_SHA = '831c1fbcf49ef92d8aff1ce9b95cbd2a78ebd75f135ef44b9f9f9b51651c8625'
ORIGINAL_SHA = '91d9392acb58ae737203bc8385f51bb01a13e670cdea47b8c808e31d4e943872'
EXECUTION_REPOSITORY = 'alectionary/alpoge-rh-replay'
OPTIONS = {'autoImplicit': False, 'relaxedAutoImplicit': False, 'maxSynthPendingDepth': 3,
           'pp.unicode.fun': True, 'maxHeartbeats': 4000000}
TRACE_RELATIVE_PATH = '.profile-diagnostic/declaration-profile.json'
TRACE_MAX_BYTES = 16 * 1024 * 1024
PROFILE_SPEC = {
    'arguments': ['--profile', '-Dprofiler.threshold=100', '-Dtrace.profiler=true',
                  '-Dtrace.profiler.threshold=1000000', '-Dtrace.Elab.definition.value=true',
                  '-Dtrace.profiler.output.pp=true'],
    'threshold_ms': 100, 'trace_output_relative_path': TRACE_RELATIVE_PATH,
    'trace_max_bytes': TRACE_MAX_BYTES, 'trace_format': 'lean-firefox-preprocessed-v48',
}
VALUE_LABEL_PREFIX = 'Elab.definition.value: '
SELECTED_DECLARATIONS = tuple('Formalism.FourierDecayAlt.P.EtaleIntegralityFacts.' + name for name in (
    'first_cofactor_norm_le', 'remainder_norm_le', 'first_cofactor_derivative_bound',
    'remainder_derivative_bound', 'card_range_inf_torsion_le_index_pow'))


def profile_arguments(workspace):
    return PROFILE_SPEC['arguments'] + ['-Dtrace.profiler.output=' + str(Path(workspace) / TRACE_RELATIVE_PATH)]


def load_core():
    # Check lexical ancestors and bytes before executing even the trusted helpers.
    import hashlib
    path = Path(__file__).absolute().parent / 'benchmark_core.py'
    for item in [*reversed(path.parents), path]:
        mode = item.lstat().st_mode
        if stat.S_ISLNK(mode) or (item != path and not stat.S_ISDIR(mode)):
            raise ValueError('Unsafe core path.')
    if not stat.S_ISREG(path.stat().st_mode) or hashlib.sha256(path.read_bytes()).hexdigest() != CORE_SHA:
        raise ValueError('Pinned common helper bytes differ.')
    spec = importlib.util.spec_from_file_location('reviewed_profile_helpers', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core = load_core()
require, digest, encode = core.require, core.digest, core.encode


def strict_json(data):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'Duplicate JSON key: ' + key)
            value[key] = item
        return value
    return json.loads(data, object_pairs_hook=pairs)


def graph(manifest):
    modules = manifest['modules']
    seen, pending = set(), [TARGET]
    while pending:
        mid = pending.pop()
        require(mid in modules, 'Missing closure module.')
        if mid not in seen:
            seen.add(mid)
            pending.extend(modules[mid]['project_imports'])
    require(seen == set(modules) and len(seen) == 15, 'Wrong exact source closure.')
    require(len(modules[TARGET]['import_forms']) == 12, 'Wrong direct imports.')
    return sorted(seen)


def load_config(path, expected_sha):
    """Reject every missing/mismatched binding before creating outputs or running tools."""
    path = core.regular(path)
    raw = path.read_bytes()
    require(core.sha(expected_sha) and digest(raw) == expected_sha, 'Config digest differs.')
    config = strict_json(raw)
    require(set(config) == {'schema_version', 'mode', 'baseline', 'target_module', 'execution_repository',
                           'core', 'manifest', 'post_build_driver', 'profiler', 'required_reviews', 'status'},
            'Unknown profile config fields; benchmark/candidate modes are rejected.')
    require(type(config['schema_version']) is int and config['schema_version'] == 1 and
            config['mode'] == 'baseline_profile_only', 'Wrong profile schema/mode.')
    require(config['baseline'] == {'repository': 'leanprover-community/riemann-hypothesis', 'commit': BASE}, 'Wrong profile baseline.')
    require(config['target_module'] == TARGET and config['execution_repository'] == EXECUTION_REPOSITORY,
            'Unbound/wrong target or execution repository.')
    require(config['core'] == {'path': 'benchmark_core.py', 'sha256': CORE_SHA}, 'Wrong common core binding.')
    require(digest(core.relative_file(path.parent, 'benchmark_core.py').read_bytes()) == CORE_SHA, 'Common core bytes changed.')
    require(config['manifest'] == {'path': 'source-manifest.json', 'sha256': MANIFEST_SHA}, 'Wrong manifest binding.')
    manifest_bytes = core.relative_file(path.parent, 'source-manifest.json').read_bytes()
    require(digest(manifest_bytes) == MANIFEST_SHA, 'Manifest bytes changed.')
    manifest = strict_json(manifest_bytes)
    require(manifest['source_commit'] == BASE and manifest['target'] == TARGET, 'Wrong manifest source.')
    require(manifest['config_files'] == core.PINNED_FILES, 'Canonical pins changed.')
    require(manifest['modules'][TARGET]['sha256'] == ORIGINAL_SHA, 'Wrong original target.')
    for mid, row in manifest['modules'].items():
        require(row['path'] == 'src/' + mid.replace('.', '/') + '.lean' and core.sha(row['sha256']), 'Bad source path/hash.')
    graph(manifest)
    require(config['post_build_driver'] == {'path': 'post-build-check.lean', 'sha256': DRIVER_SHA}, 'Wrong type/axiom driver binding.')
    driver = core.relative_file(path.parent, 'post-build-check.lean').read_bytes()
    require(digest(driver) == DRIVER_SHA, 'Type/axiom driver bytes changed.')
    require(encode(config['profiler']) == encode(PROFILE_SPEC), 'Named profiler spec differs.')
    require(set(config['required_reviews']) == {'root_method', 'independent_method'} and
            all(core.sha(value) for value in config['required_reviews'].values()), 'Method review remains unbound.')
    require(isinstance(config['status'], str), 'Invalid descriptive status.')
    return config, manifest, driver, raw


def descriptors(directory, names):
    return {name: {'bytes': core.regular(directory / name).stat().st_size,
                   'sha256': digest(core.regular(directory / name).read_bytes())}
            for name in names if (directory / name).exists()}


def write_new(path, data):
    path = core.path_checked(path, missing=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    core.path_checked(path.parent)
    with path.open('xb') as stream:
        stream.write(data)


def fetch_current(config, relative, wanted, env, budget, output, index):
    # Deliberately does not call the old core.fetch_input (which pins1b894).
    url = 'https://raw.githubusercontent.com/' + config['baseline']['repository'] + '/' + BASE + '/' + relative
    maximum = core.timeout_for(budget, 120)
    command = ['curl', '--fail', '--location', '--silent', '--show-error', '--max-time', str(maximum),
               '--max-filesize', '2097152', url]
    failure = None
    try:
        result = subprocess.run(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                check=False, timeout=maximum)
    except subprocess.TimeoutExpired as error:
        # subprocess.run has killed/waited for the process; keep both partial streams.
        result = subprocess.CompletedProcess(command, None, error.stdout or b'', error.stderr or b'')
        failure = 'TimeoutExpired'
    prefix = f'fetch/{index:02d}'
    write_new(output / (prefix + '.stdout.log'), result.stdout)
    write_new(output / (prefix + '.stderr.log'), result.stderr)
    with (output / 'fetch-inputs.log').open('ab') as log:
        log.write(encode({'command': command, 'exit_code': result.returncode, 'stdout': prefix + '.stdout.log',
                          'stderr': prefix + '.stderr.log', 'source_path': relative, 'error_type': failure}))
    require(result.returncode == 0, 'Source HTTP request failed; raw response retained.')
    require(len(result.stdout) <= 2 * 1024 * 1024 and digest(result.stdout) == wanted, 'Source digest differs: ' + relative)
    return result.stdout


def verify_sources(workspace, manifest, expected):
    core.input_seal(workspace, expected)
    for mid, row in manifest['modules'].items():
        data = core.relative_file(workspace, row['path']).read_bytes()
        require(len(data) == row['bytes'] and len(data.splitlines()) == row['lines'], 'Source size/line count differs.')
        require(core.import_rows(data) == row['import_forms'], 'Actual source imports differ.')
    original = core.relative_file(workspace, manifest['modules'][TARGET]['path']).read_bytes()
    require(original.startswith(b'module\n') and digest(original) == ORIGINAL_SHA, 'Original module header/body differs.')


def verify_seals(workspace, manifest, expected, packages, compiled, env, budget):
    verify_sources(workspace, manifest, expected)
    require(core.package_identity(workspace, env, budget) == packages, 'Package identity changed.')
    require(core.artifact_rows(workspace, exclude_target=False, target=TARGET, budget=budget) == compiled,
            'Warm compiled artifacts changed (including original target).')


def diagnostic_artifacts(workspace, diagnostic_library, started_ns):
    base = diagnostic_library / Path(*TARGET.split('.'))
    rows = {}
    for path in sorted(diagnostic_library.rglob('*')):
        core.path_checked(path)
        if path.is_dir():
            continue
        path = core.regular(path)
        require(path.parent == base.parent and path.name.startswith(base.name + '.') and
                path.name[len(base.name):] in core.COMPILED_SUFFIXES, 'Unexpected diagnostic artifact.')
        info = path.stat()
        require(info.st_size > 0 and info.st_mtime_ns >= started_ns, 'Stale/empty diagnostic output.')
        rows[path.relative_to(workspace).as_posix()] = {'bytes': info.st_size, 'sha256': digest(path.read_bytes()),
                                                     'mtime_ns': info.st_mtime_ns}
    require(all(str(base.relative_to(workspace)) + suffix in rows for suffix in ('.olean', '.olean.private', '.olean.server')),
            'Incomplete fresh diagnostic OLean family.')
    return rows


def parse_profile(stdout, stderr, workspace, diagnostic_olean, toolchain_bin):
    setups, commands, took, cumulative = [], [], [], []
    marker_count = 0
    number = r'(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
    for stream_name, data in [('stdout', stdout), ('stderr', stderr)]:
        lines = data.decode().splitlines()
        in_cumulative = False
        for index, line in enumerate(lines, 1):
            if 'module setup: ' in line:
                prefix, raw = line.split('module setup: ', 1)
                require(prefix.strip() in ('', 'info:', 'trace:'), 'Unknown setup log prefix.')
                setup = strict_json(raw)
                require(setup.get('name') == TARGET and setup.get('isModule') is True, 'Wrong module setup identity.')
                require(encode(setup.get('options')) == encode(OPTIONS), 'Canonical options differ or overwrite profiler.')
                require('imports' not in setup and isinstance(setup.get('importArts'), dict) and setup['importArts'],
                        'Missing/overridden module imports.')
                require(TARGET not in setup['importArts'], 'Profile setup imports its own warm target.')
                setups.append((raw.encode(), setup))
            if str(toolchain_bin / 'lean') in line:
                tokens = shlex.split(line)
                if str(toolchain_bin / 'lean') in tokens:
                    pos = tokens.index(str(toolchain_bin / 'lean'))
                    args = tokens[pos + 1:]
                    target_sources = (str(workspace / ('src/' + TARGET.replace('.', '/') + '.lean')),
                                      'src/' + TARGET.replace('.', '/') + '.lean')
                    is_target = any(arg in target_sources for arg in args)
                    is_diagnostic = str(diagnostic_olean) in args
                    if not is_target and not is_diagnostic:
                        continue  # Lake may replay dependency build logs; they stay in the raw stream.
                    require(is_target and is_diagnostic, 'Unexpected target/diagnostic compiler invocation.')
                    require(len(args) == 4 + len(profile_arguments(workspace)) + 2 and
                            args[0] == '--tstack=400000' and args[2] == '--setup' and
                            args[4:] == profile_arguments(workspace) + ['-o', str(diagnostic_olean)], 'Verbose compiler arguments differ.')
                    require(args[1] in target_sources, 'Wrong verbose compiler source.')
                    require(Path(args[3]).is_absolute() and '..' not in Path(args[3]).parts, 'Unsafe generated setup path.')
                    commands.append({'line': line, 'argv': tokens[pos:]})
            hit = re.fullmatch(r'(.+?) took (' + number + r')(ms|s)', line)
            if hit:
                seconds = float(hit[2]) / (1000 if hit[3] == 'ms' else 1)
                require(math.isfinite(seconds) and seconds >= 0, 'Invalid profiler duration.')
                took.append({'stream': stream_name, 'line': index, 'text': line, 'seconds': seconds})
            if line == 'cumulative profiling times:':
                marker_count += 1
                in_cumulative = True
                continue
            if in_cumulative:
                hit = re.fullmatch(r'\s+(.+?) (' + number + r')(ms|s)', line)
                if hit:
                    seconds = float(hit[2]) / (1000 if hit[3] == 'ms' else 1)
                    require(math.isfinite(seconds) and seconds >= 0, 'Invalid cumulative duration.')
                    cumulative.append({'stream': stream_name, 'line': index, 'category': hit[1], 'seconds': seconds,
                                       'text': line})
                elif line.strip():
                    in_cumulative = False
    require(len(setups) == len(commands) == 1, 'Missing/duplicate actual setup or verbose compiler line.')
    require(marker_count == 1 and took and cumulative, 'Missing actual profiler markers/rows.')
    return setups[0], commands[0], {'threshold_ms': 100, 'took_rows': took, 'cumulative': cumulative,
                                  'scope': 'Thresholded exclusive category/event attribution; not one row per theorem, serialized bytes, memory or comparative speed.'}


def setup_project_bindings(setup, workspace, compiled, modules):
    """Bind the actual setup's variable-length artifact arrays to sealed warm files."""
    bindings = {}
    for mid in modules:
        if mid == TARGET:
            continue
        parts = setup['importArts'].get(mid)
        require(isinstance(parts, list) and len(parts) == 2 and all(isinstance(part, list) for part in parts),
                'Malformed project import artifact arrays.')
        require(1 <= len(parts[0]) <= 3 and len(parts[1]) <= 2, 'Missing/excess project import artifacts.')
        names = []
        for values, suffixes in zip(parts, [('.olean', '.olean.server', '.olean.private'), ('.ir.sig', '.ir')]):
            for reference, suffix in zip(values, suffixes):
                require(isinstance(reference, str) and reference and '..' not in Path(reference).parts,
                        'Unsafe setup artifact reference.')
                path = Path(os.path.abspath(workspace / reference))
                require(path.is_relative_to(workspace), 'Project setup artifact outside canonical workspace.')
                relative = path.relative_to(workspace).as_posix()
                require(relative == '.lake/build/lib/lean/' + mid.replace('.', '/') + suffix and relative in compiled,
                        'Setup project artifact is not the sealed warm artifact.')
                names.append(relative)
        bindings[mid] = names
    return bindings


def source_declarations(source):
    """A closed-source inventory, not a general Lean parser or namespace filter."""
    require(digest(source) == ORIGINAL_SHA, 'Declaration mapping requires the exact original source.')
    blocks, namespace, result = [], [], {}
    for line_number, line in enumerate(source.decode().splitlines(), 1):
        text = line.strip()
        if text.startswith('namespace '):
            name = text[len('namespace '):]
            blocks.append(('namespace', name))
            namespace.append(name)
        elif re.fullmatch(r'(?:@\[[^]]*\]\s+)?(?:public\s+)?(?:noncomputable\s+)?section(?:\s+\w+)?', text):
            name = text.split('section', 1)[1].strip()
            blocks.append(('section', name))
        elif re.fullmatch(r'end(?:\s+[A-Za-z0-9_.]+)?', text):
            require(bool(blocks), 'Unmatched source scope.')
            kind, name = blocks.pop()
            require(text == 'end' or text[4:] == name, 'Source scope mapping differs.')
            if kind == 'namespace':
                namespace.pop()
        match = re.match(r'^(?:(?:noncomputable|private|protected)\s+)?(theorem|lemma|def)\s+(\S+)', text)
        if match:
            kind, name = match.groups()
            full_name = name if name.startswith('Formalism.') else '.'.join(namespace + [name])
            require(full_name not in result, 'Duplicate mapped source declaration.')
            result[full_name] = {'kind': kind, 'line': line_number}
    require(len(result) == 136 and sum(row['kind'] in ('theorem', 'lemma') for row in result.values()) == 125,
            'Original declaration inventory differs.')
    return result


def parse_declaration_trace(raw, source):
    """Read the exact611c exporter, attributing positive sample weights by stack ancestry."""
    require(isinstance(raw, bytes) and 0 < len(raw) <= TRACE_MAX_BYTES, 'Named trace exceeds the bounded byte limit.')
    data = strict_json(raw)
    owned = source_declarations(source)
    categories = [{'name': name, 'color': color, 'subcategories': []} for name, color in (
        ('Other', 'gray'), ('Elab.async', 'gray'), ('Elab.block', 'brown'),
        ('Elab', 'red'), ('Meta', 'yellow'), ('Kernel', 'green'))]
    require(set(data) == {'meta', 'libs', 'threads'} and data['libs'] == [], 'Unexpected exporter envelope.')
    meta = data['meta']
    require(set(meta) == {'interval', 'startTime', 'categories', 'processType', 'product',
                          'preprocessedProfileVersion', 'markerSchema', 'sampleUnits'}, 'Unexpected exporter metadata.')
    require(meta['categories'] == categories and meta['product'] == 'lean' and
            type(meta['processType']) is int and meta['processType'] == 0 and
            type(meta['preprocessedProfileVersion']) is int and meta['preprocessedProfileVersion'] == 48 and
            meta['markerSchema'] == [] and meta['sampleUnits'] == {'time': 'ms', 'eventDelay': 'ms', 'threadCPUDelta': 'µs'},
            'Wrong exporter version/units/categories.')

    def number(value):
        require(type(value) in (int, float) and math.isfinite(value) and value >= 0, 'Invalid negative/nonfinite trace number.')
        return value

    require(number(meta['interval']) == 0, 'Unexpected tracing sample interval.')
    number(meta['startTime'])

    def index(value, bound):
        require(type(value) is int and 0 <= value < bound, 'Invalid trace table index.')

    def table(thread, name, columns, empty_columns=()):
        value = thread[name]
        require(isinstance(value, dict) and set(value) == {'length', *columns, *empty_columns}, 'Unexpected trace table columns: ' + name)
        length = value['length']
        require(type(length) is int and 0 <= length <= 100000, 'Trace table length exceeds the bound.')
        require(all(isinstance(value[key], list) and len(value[key]) == length for key in columns), 'Trace column length differs: ' + name)
        require(all(value[key] == [] for key in empty_columns), 'Exporter placeholder columns must be empty.')
        return value

    threads = data['threads']
    require(isinstance(threads, list) and 0 < len(threads) <= 128, 'Missing/excess trace threads.')
    output, identities, observed, positive_known = [], set(), set(), set()
    for ordinal, thread in enumerate(threads):
        require(set(thread) == {'name', 'processType', 'isMainThread', 'samples', 'markers', 'stackTable', 'frameTable',
                                'resourceTable', 'nativeSymbols', 'stringArray', 'funcTable'}, 'Unexpected thread fields.')
        require(isinstance(thread['name'], str) and thread['name'] and type(thread['isMainThread']) is bool and
                thread['processType'] == 'default', 'Wrong thread identity.')
        if thread['isMainThread']:
            require(thread['name'] == TARGET, 'Named trace main module identity differs.')
            tid = 0
        else:
            require(re.fullmatch('[1-9][0-9]*', thread['name']) is not None, 'Invalid exported worker identity.')
            tid = int(thread['name'])
        require(tid not in identities, 'Duplicate exported thread identity.')
        identities.add(tid)
        require(thread['markers'] == {'data': [], 'name': [], 'length': 0} and
                thread['resourceTable'] == {'type': [], 'length': 0} and thread['nativeSymbols'] == {'type': [], 'length': 0},
                'Unexpected exporter resource/marker data.')
        require(all(type(thread[key]['length']) is int for key in ('markers', 'resourceTable', 'nativeSymbols')),
                'Invalid resource/marker length type.')
        strings = thread['stringArray']
        require(isinstance(strings, list) and len(strings) <= 100000 and all(isinstance(value, str) for value in strings), 'Invalid trace strings.')
        functions = table(thread, 'funcTable', ['name', 'resource', 'fileName', 'lineNumber', 'columnNumber'], ['isJS', 'relevantForJS'])
        frames = table(thread, 'frameTable', ['address', 'inlineDepth', 'category', 'subcategory', 'func', 'nativeSymbol',
                                             'innerWindowID', 'implementation', 'line', 'column'])
        require(frames['length'] == functions['length'] and frames['func'] == list(range(functions['length'])),
                'Pinned exporter function/frame identity alignment differs.')
        stacks = table(thread, 'stackTable', ['frame', 'category', 'subcategory', 'prefix'])
        samples = thread['samples']
        require(samples.get('weightType') == 'tracing-ms', 'Wrong sample weighting units.')
        sample_columns = ['stack', 'time', 'weight', 'threadCPUDelta']
        require(set(samples) == {'length', 'weightType', *sample_columns} and type(samples['length']) is int and
                0 <= samples['length'] <= 200000 and
                all(isinstance(samples[key], list) and len(samples[key]) == samples['length'] for key in sample_columns),
                'Invalid sample table dimensions.')
        named = {}
        for function_index in range(functions['length']):
            string_index = functions['name'][function_index]
            index(string_index, len(strings))
            require(type(functions['resource'][function_index]) is int and functions['resource'][function_index] == -1 and
                    all(functions[key][function_index] is None for key in ('fileName', 'lineNumber', 'columnNumber')),
                    'Unexpected function resources/source-position data.')
            label = strings[string_index]
            if label.startswith(VALUE_LABEL_PREFIX):
                name = label[len(VALUE_LABEL_PREFIX):]
                require(bool(name), 'Empty named-value label.')
                if name not in named:
                    named[name] = {'name': name, 'label': label, 'function_indexes': [], 'source_owned': name in owned,
                                   'source_kind': owned[name]['kind'] if name in owned else None,
                                   'source_header_line': owned[name]['line'] if name in owned else None,
                                   'inclusive_weight_ms': 0.0, 'sample_memberships': 0, 'positive_weight_samples': 0}
                named[name]['function_indexes'].append(function_index)
                observed.add(name)
        for frame_index in range(frames['length']):
            index(frames['func'][frame_index], functions['length'])
            category = frames['category'][frame_index]
            if category is not None:
                index(category, len(categories))
            require(type(frames['address'][frame_index]) is int and frames['address'][frame_index] == -1 and
                    type(frames['inlineDepth'][frame_index]) is int and frames['inlineDepth'][frame_index] == 0 and
                    all(frames[key][frame_index] is None for key in ('subcategory', 'nativeSymbol', 'innerWindowID', 'implementation', 'line', 'column')),
                    'Unexpected exporter frame metadata.')
        for stack_index in range(stacks['length']):
            index(stacks['frame'][stack_index], frames['length'])
            index(stacks['category'][stack_index], len(categories))
            require(type(stacks['subcategory'][stack_index]) is int and stacks['subcategory'][stack_index] == 0,
                    'Unexpected stack subcategory.')
            if stacks['prefix'][stack_index] is not None:
                index(stacks['prefix'][stack_index], stacks['length'])
        # Resolve all chains iteratively, including unused stacks; cycles cannot hide.
        ancestry, depths, state = {}, {}, [0] * stacks['length']
        for stack_index in range(stacks['length']):
            chain, current = [], stack_index
            while current is not None and current not in ancestry:
                require(state[current] == 0, 'Cycle in trace stack ancestry.')
                state[current] = 1
                chain.append(current)
                require(len(chain) <= 2048, 'Trace ancestry exceeds the bounded depth.')
                current = stacks['prefix'][current]
            while chain:
                current = chain.pop()
                parent = stacks['prefix'][current]
                names = ancestry[parent] if parent is not None else frozenset()
                depth = 1 + (depths[parent] if parent is not None else 0)
                require(depth <= 2048, 'Trace ancestry exceeds the bounded depth.')
                function_index = frames['func'][stacks['frame'][current]]
                label = strings[functions['name'][function_index]]
                if label.startswith(VALUE_LABEL_PREFIX):
                    names = names | {label[len(VALUE_LABEL_PREFIX):]}
                ancestry[current], depths[current], state[current] = names, depth, 2
        total, unattributed, positive_samples = 0.0, 0.0, 0
        for sample_index in range(samples['length']):
            stack_index = samples['stack'][sample_index]
            index(stack_index, stacks['length'])
            number(samples['time'][sample_index])  # Not globally monotone: zero-weight root gaps may overlap.
            weight = number(samples['weight'][sample_index])
            number(samples['threadCPUDelta'][sample_index])  # Synthetic elapsed microseconds, never CPU usage.
            names = ancestry[stack_index]
            if weight > 0:
                total += weight
                positive_samples += 1
                if not names:
                    unattributed += weight
            for name in names:  # Set membership counts a repeated named ancestor only once per sample.
                row = named[name]
                row['sample_memberships'] += 1
                if weight > 0:
                    row['inclusive_weight_ms'] += weight
                    row['positive_weight_samples'] += 1
                    if name in owned:
                        positive_known.add(name)
        require(math.isfinite(total) and math.isfinite(unattributed) and
                all(math.isfinite(row['inclusive_weight_ms']) for row in named.values()), 'Trace duration aggregate overflow.')
        output.append({'thread_index': ordinal, 'thread_id': tid, 'name': thread['name'], 'is_main_thread': thread['isMainThread'],
                       'sample_count': samples['length'], 'positive_weight_samples': positive_samples,
                       'total_positive_weight_ms': total, 'unattributed_positive_weight_ms': unattributed,
                       'named_value_rows': [named[name] for name in sorted(named)]})
    require(0 in identities, 'Named trace is missing its original-module main thread.')
    require(bool(positive_known), 'No positive source-owned named value attribution.')
    return {'schema': 'lean611c-named-value-attribution-v1', 'source_sha256': ORIGINAL_SHA, 'source_declaration_count': len(owned),
            'units': 'milliseconds', 'threads': output, 'observed_named_values': sorted(observed),
            'known_source_positive_name_count': len(positive_known),
            'selected_declaration_coverage': [{'name': name, 'source_header_line': owned[name]['line'], 'named_frame_present': name in observed,
                                                'positive_weight_present': name in positive_known} for name in SELECTED_DECLARATIONS],
            'scope': 'Inclusive instrumented value-elaboration weights by named ancestry within each exported thread. Rows may overlap; do not sum across names/threads. Counts are sample memberships, never invocations. Static source header lines are not timing positions; unknown/private/generated names are retained unmapped. No total declaration/kernel/codegen/memory/comparative-speed claim.'}


def capture_declaration_trace(workspace, output, started_ns):
    path = core.regular(workspace / TRACE_RELATIVE_PATH)
    before = path.stat()
    require(0 < before.st_size <= TRACE_MAX_BYTES and before.st_mtime_ns >= started_ns, 'Missing/oversized/stale declaration trace.')
    raw = path.read_bytes()
    after = path.stat()
    require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns) and len(raw) == before.st_size,
            'Declaration trace changed during capture.')
    retained = output / 'declaration-profile.json'
    if retained.exists():
        require(core.regular(retained).read_bytes() == raw, 'Retained declaration trace differs.')
    else:
        write_new(retained, raw)
    return {'path': 'profile/declaration-profile.json', 'bytes': len(raw), 'sha256': digest(raw), 'mtime_ns': before.st_mtime_ns}


def verify_declaration_trace(workspace, descriptor):
    path = core.regular(workspace / TRACE_RELATIVE_PATH)
    info = path.stat()
    require(info.st_size == descriptor['bytes'] and info.st_mtime_ns == descriptor['mtime_ns'] and
            digest(path.read_bytes()) == descriptor['sha256'], 'Original declaration trace changed across overlay/postcheck.')


def profile_module(workspace, output, manifest, expected, packages, compiled, env, toolchain_bin, budget):
    output.mkdir()
    diagnostic = core.path_checked(workspace / '.profile-diagnostic', missing=True)
    require(not diagnostic.exists(), 'Fresh empty diagnostic directory required.')
    diagnostic.mkdir()
    library = diagnostic / 'lib/lean'
    olean = library / Path(*TARGET.split('.')).with_suffix('.olean')
    olean.parent.mkdir(parents=True)
    verify_seals(workspace, manifest, expected, packages, compiled, env, budget)
    require(not list(library.rglob('*.*')), 'Diagnostic library was not empty.')
    command = core.sandbox_prefix(workspace) + ['lake', '-v', 'lean', manifest['modules'][TARGET]['path'], '--'] + profile_arguments(workspace) + ['-o', str(olean)]
    result = {'status': 'preparing', 'command': command, 'environment': env, 'diagnostic_library': str(library),
              'start_ns': time.time_ns(), 'publication_approved': False, 'full_proof_verified': False}
    started = time.monotonic()
    try:
        with (output / 'stdout.log').open('wb') as stdout, (output / 'stderr.log').open('wb') as stderr:
            process = subprocess.run(command, cwd=workspace, env=env, stdout=stdout, stderr=stderr,
                                     check=False, timeout=core.timeout_for(budget, 300))
        result.update(exit_code=process.returncode, monotonic_wall_seconds=time.monotonic() - started)
        result['declaration_trace'] = capture_declaration_trace(workspace, output, result['start_ns'])
        require(process.returncode == 0, 'Actual profile command failed.')
        (raw, setup), compiler, stats = parse_profile((output / 'stdout.log').read_bytes(), (output / 'stderr.log').read_bytes(),
                                                    workspace, olean, toolchain_bin)
        write_new(output / 'module-setup.json', raw)
        result['module_setup'] = {'path': 'profile/module-setup.json', 'sha256': digest(raw), 'bytes': len(raw)}
        result.update(verbose_compiler_line=compiler['line'], compiler_argv=compiler['argv'], profiler_statistics=stats)
        raw_trace = (output / 'declaration-profile.json').read_bytes()
        summary = parse_declaration_trace(raw_trace, core.relative_file(workspace, manifest['modules'][TARGET]['path']).read_bytes())
        require(summary['known_source_positive_name_count'] > 0, 'No positive source-owned named value attribution.')
        summary_bytes = encode(summary)
        write_new(output / 'declaration-summary.json', summary_bytes)
        result['declaration_summary'] = {'path': 'profile/declaration-summary.json', 'bytes': len(summary_bytes), 'sha256': digest(summary_bytes)}
        result['named_value_summary'] = summary
        result['setup_project_bindings'] = setup_project_bindings(setup, workspace, compiled, graph(manifest))
        result['fresh_artifacts'] = diagnostic_artifacts(workspace, library, result['start_ns'])
        verify_seals(workspace, manifest, expected, packages, compiled, env, budget)
        verify_declaration_trace(workspace, result['declaration_trace'])
        result['status'] = 'completed'
    except Exception as error:
        result.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        result.setdefault('monotonic_wall_seconds', time.monotonic() - started)
        result['controller_interval_seconds'] = time.monotonic() - started
        result['wall_scope'] = 'Instrumented subprocess interval; parsing/seal overhead is separate, no comparative inference.'
        if 'declaration_trace' not in result:
            try:
                (workspace / TRACE_RELATIVE_PATH).lstat()
                result['declaration_trace'] = capture_declaration_trace(workspace, output, result['start_ns'])
            except FileNotFoundError:
                pass
            except Exception as error:
                result['trace_capture_error'] = str(error)
        result['retained_logs'] = descriptors(output, ['stdout.log', 'stderr.log', 'module-setup.json',
                                                       'declaration-profile.json', 'declaration-summary.json'])
        (output / 'result.json').write_bytes(encode(result))
    return result


def overlay_dependencies(workspace, library, compiled, manifest, fresh):
    """Complete the Formalism root without linking or replacing profiled outputs."""
    source_root = '.lake/build/lib/lean/'
    target_base = source_root + TARGET.replace('.', '/')
    owners = {source_root + mid.replace('.', '/'): mid for mid in graph(manifest) if mid != TARGET}
    rows = {}
    for name, source in compiled.items():
        if not name.startswith(source_root + 'Formalism/'):
            continue
        if name.startswith(target_base + '.'):
            continue
        matches = [base for base in owners if name.startswith(base + '.') and
                   str(PurePosixPath(name).parent) == str(PurePosixPath(base).parent)]
        require(len(matches) == 1, 'Warm Formalism artifact outside exact dependency closure.')
        suffix = name[len(matches[0]):]
        require(suffix in core.COMPILED_SUFFIXES, 'Unexpected compiled dependency suffix.')
        path = core.relative_file(workspace, name)
        data = path.read_bytes()
        require(len(data) == source['bytes'] and digest(data) == source['sha256'], 'Overlay source differs from warm seal.')
        destination = library / name[len(source_root):]
        require(not destination.exists(), 'Overlay would overwrite a diagnostic artifact.')
        write_new(destination, data)
        info = core.regular(destination).stat()
        require(digest(destination.read_bytes()) == source['sha256'], 'Copied overlay bytes differ.')
        rows[destination.relative_to(workspace).as_posix()] = {
            'source_path': name, 'source_bytes': source['bytes'], 'source_sha256': source['sha256'],
            'bytes': info.st_size, 'sha256': digest(data), 'mtime_ns': info.st_mtime_ns}
    for base in owners:
        require(all(any(row['source_path'] == base + suffix for row in rows.values())
                    for suffix in ('.olean', '.olean.private', '.olean.server')), 'Dependency overlay family incomplete.')
    verify_library(workspace, library, fresh, rows)
    return rows


def verify_library(workspace, library, fresh, overlay):
    expected = dict(fresh)
    expected.update({name: {key: row[key] for key in ('bytes', 'sha256', 'mtime_ns')} for name, row in overlay.items()})
    require(len(expected) == len(fresh) + len(overlay), 'Overlay overlaps the profiled target.')
    actual = {}
    for path in sorted(library.rglob('*')):
        core.path_checked(path)
        if path.is_dir():
            continue
        path = core.regular(path)
        info = path.stat()
        actual[path.relative_to(workspace).as_posix()] = {'bytes': info.st_size, 'sha256': digest(path.read_bytes()),
                                                       'mtime_ns': info.st_mtime_ns}
    require(actual == expected, 'Profiled target or complete diagnostic overlay changed.')
    for name, row in overlay.items():
        source = core.relative_file(workspace, row['source_path'])
        require(source.stat().st_size == row['source_bytes'] == row['bytes'] and
                digest(source.read_bytes()) == row['source_sha256'] == row['sha256'], 'Overlay source binding differs.')


def validate_post_path(value, library, captured, workspace):
    require(isinstance(captured, str) and captured and '\n' not in captured and '\r' not in captured, 'Invalid captured LEAN_PATH.')
    parts = captured.split(os.pathsep)
    require(all(part and '..' not in Path(part).parts for part in parts), 'Unsafe/empty LEAN_PATH component.')
    normalized = [str(Path(os.path.abspath(workspace / part))) for part in parts]
    require(str(library) not in normalized and str(workspace / '.lake/build/lib/lean') in normalized,
            'Missing canonical warm library path.')
    require(value == str(library) + os.pathsep + captured, 'Profiled complete library must be first in LEAN_PATH.')


def post_check_profile(workspace, output, driver, manifest, expected, packages, compiled, env,
                       toolchain_bin, library, fresh, overlay, budget):
    output.mkdir()
    write_new(workspace / 'BenchmarkPostCheck.lean', driver)
    write_new(output / 'driver.lean', driver)
    probe_command = core.sandbox_prefix(workspace) + ['lake', 'env', 'printenv', 'LEAN_PATH']
    result = {'status': 'preparing', 'driver_sha256': digest(driver), 'publication_approved': False,
              'full_proof_verified': False, 'timing_scope': 'After profiling, outside attribution interval'}
    try:
        verify_library(workspace, library, fresh, overlay)
        verify_seals(workspace, manifest, expected, packages, compiled, env, budget)
        with (output / 'lean-path.stdout.log').open('wb') as stdout, (output / 'lean-path.stderr.log').open('wb') as stderr:
            probe = subprocess.run(probe_command, cwd=workspace, env=env, stdout=stdout, stderr=stderr,
                                   check=False, timeout=core.timeout_for(budget, 30))
        result['lean_path_probe'] = {'command': probe_command, 'environment': env, 'exit_code': probe.returncode}
        require(probe.returncode == 0, 'Trusted Lake LEAN_PATH probe failed.')
        raw_path = (output / 'lean-path.stdout.log').read_bytes().decode()
        require(raw_path.endswith('\n') and raw_path.count('\n') == 1, 'Unexpected LEAN_PATH probe output.')
        captured = raw_path[:-1]
        post_env = dict(env, LEAN_PATH=str(library) + os.pathsep + captured)
        validate_post_path(post_env['LEAN_PATH'], library, captured, workspace)
        result['lean_path_probe']['LEAN_PATH'] = captured
        command = core.sandbox_prefix(workspace) + [str(toolchain_bin / 'lean'), 'BenchmarkPostCheck.lean']
        result.update(command=command, environment=post_env)
        with (output / 'stdout.log').open('wb') as stdout, (output / 'stderr.log').open('wb') as stderr:
            process = subprocess.run(command, cwd=workspace, env=post_env, stdout=stdout, stderr=stderr,
                                     check=False, timeout=core.timeout_for(budget, 120))
        result['exit_code'] = process.returncode
        require(process.returncode == 0, 'Profiled-output original-type/axiom driver failed.')
        require('sorryAx' not in (output / 'stderr.log').read_text(), 'Admission in driver diagnostics.')
        result['axioms'] = core.parse_axioms((output / 'stdout.log').read_text())
        require(result['axioms'] == {name: sorted(core.ALLOWED_AXIOMS) for name in core.CHECK_DECLARATIONS},
                'Original DB.pi actual axiom inventory differs.')
        verify_library(workspace, library, fresh, overlay)
        verify_seals(workspace, manifest, expected, packages, compiled, env, budget)
        result['status'] = 'completed'
    except Exception as error:
        result.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        result['files'] = descriptors(output, ['driver.lean', 'stdout.log', 'stderr.log', 'lean-path.stdout.log', 'lean-path.stderr.log'])
        if 'lean_path_probe' in result:
            result['lean_path_probe']['files'] = {name: result['files'][name] for name in ('lean-path.stdout.log', 'lean-path.stderr.log') if name in result['files']}
        (output / 'result.json').write_bytes(encode(result))
    return result


def run(config_path, config_sha, workspace, output):
    config, manifest, driver, raw_config = load_config(config_path, config_sha)
    require(os.environ.get('GITHUB_REPOSITORY') == EXECUTION_REPOSITORY and
            os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch', 'Wrong repository/event.')
    require(re.fullmatch('[0-9a-f]{40}', os.environ.get('EXPECTED_HELPER_COMMIT', '')) and
            os.environ.get('GITHUB_SHA') == os.environ['EXPECTED_HELPER_COMMIT'], 'Wrong exact helper.')
    require(os.environ.get('EXPECTED_CONFIG_SHA256') == config_sha and
            re.fullmatch('[1-9][0-9]*', os.environ.get('GITHUB_RUN_ID', '')) and
            os.environ.get('GITHUB_RUN_ATTEMPT') == '1', 'Config/run/attempt identity differs.')
    budget = core.Budget(os.environ.get('BENCH_JOB_START_EPOCH', '0'))
    budget.cap(1)
    workspace, output = core.path_checked(workspace, missing=True), core.path_checked(output, missing=True)
    require(not workspace.is_relative_to(output) and not output.is_relative_to(workspace), 'Evidence and compiler workspace must be disjoint.')
    require(not workspace.exists() and not output.exists(), 'Fresh workspace/output required; retain failed attempts.')
    workspace.mkdir(parents=True)
    output.mkdir(parents=True)
    write_new(output / 'config.json', raw_config)
    write_new(output / 'source-manifest.json', core.relative_file(config_path.parent, 'source-manifest.json').read_bytes())
    receipt = {'schema': 'baseline-original-profile-v1', 'schema_version': 1, 'mode': 'baseline_profile_only',
               'status': 'preparing', 'config_sha256': config_sha, 'controller_sha256': digest(core.regular(__file__).read_bytes()),
               'core_sha256': CORE_SHA, 'expected_helper_commit': os.environ['EXPECTED_HELPER_COMMIT'],
               'workflow_budget_start_epoch': os.environ['BENCH_JOB_START_EPOCH'], 'controller_deadline_minutes': 50,
               'github': {key: os.environ.get(key) for key in ('GITHUB_REPOSITORY', 'GITHUB_SHA', 'GITHUB_RUN_ID',
                          'GITHUB_RUN_ATTEMPT', 'GITHUB_WORKFLOW_REF', 'GITHUB_EVENT_NAME')},
               'publication_approved': False, 'publication_ready': False, 'full_proof_verified': False}
    (output / 'receipt.json').write_bytes(encode(receipt))
    try:
        env = core.clean_environment(workspace)
        expected = dict(core.PINNED_FILES)
        expected.update({row['path']: row['sha256'] for row in manifest['modules'].values()})
        for index, (relative, wanted) in enumerate(expected.items(), 1):
            data = fetch_current(config, relative, wanted, env, budget, output, index)
            write_new(workspace / relative, data)
            write_new(output / 'baseline-inputs' / relative, data)
        receipt['actual_input_sha256'] = expected
        verify_sources(workspace, manifest, expected)
        modules = graph(manifest)
        receipt.update(source_graph=modules, source_import_counts={'direct': 12, 'project_dependencies': 14, 'warmed_project_modules': 15})
        (workspace / '.isolated-lake-cache').mkdir()
        binaries = {name: core.regular(subprocess.check_output(['elan', 'which', name], env=env, text=True,
                                                             timeout=core.timeout_for(budget, 30)).strip()) for name in ('lean', 'lake')}
        require(binaries['lean'].parent == binaries['lake'].parent, 'Stock toolchain roots differ.')
        toolchain_bin = binaries['lean'].parent
        env['PATH'] = str(toolchain_bin) + os.pathsep + env['PATH']
        receipt.update(stock_toolchain_bin=str(toolchain_bin), stock_binary_sha256={name: digest(path.read_bytes()) for name, path in binaries.items()},
                       environment=env)
        receipt['versions'] = {name: subprocess.check_output([str(path), '--version'], env=env, text=True,
                                                           timeout=core.timeout_for(budget, 30)).strip() for name, path in binaries.items()}
        require(receipt['versions'] == {'lean': core.LEAN, 'lake': core.LAKE}, 'Stock compiler version differs.')
        receipt['sandbox_preflight'] = core.sandbox_preflight(workspace, output / 'sandbox-preflight', env, toolchain_bin, budget)
        cache_command = ['lake', 'exe', 'mathlib/cache', 'get']
        receipt['mathlib_setup_command'] = cache_command
        with (output / 'mathlib-setup.log').open('wb') as log:
            setup = subprocess.run(cache_command, cwd=workspace, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   check=False, timeout=core.timeout_for(budget, 900))
        receipt['mathlib_setup_exit_code'] = setup.returncode
        require(setup.returncode == 0, 'Official Mathlib cache setup failed.')
        packages = core.package_identity(workspace, env, budget)
        verify_sources(workspace, manifest, expected)
        warm = output / 'warm-baseline'
        warm.mkdir()
        command = ['/usr/bin/time', '-v', '-o', str(warm / 'time-v.txt'), '--'] + core.sandbox_command(workspace, modules)
        receipt['cold_baseline_warm_command'] = command
        started = time.monotonic()
        with (warm / 'build.log').open('wb') as log:
            result = subprocess.run(command, cwd=workspace, env=env, stdout=log, stderr=subprocess.STDOUT,
                                    check=False, timeout=core.timeout_for(budget, 900))
        receipt.update(cold_baseline_warm_exit_code=result.returncode, cold_baseline_warm_wall_seconds=time.monotonic() - started)
        if (warm / 'time-v.txt').exists():
            receipt['cold_baseline_warm_metrics'] = core.time_metrics((warm / 'time-v.txt').read_bytes())
        require(result.returncode == 0 and receipt.get('cold_baseline_warm_metrics', {}).get('gnu_exit_status') == 0,
                'Original union warm-up failed.')
        require(core.package_identity(workspace, env, budget) == packages, 'Warm-up mutated packages.')
        verify_sources(workspace, manifest, expected)
        compiled = core.artifact_rows(workspace, exclude_target=False, target=TARGET, budget=budget)
        for mid in modules:
            require('.lake/build/lib/lean/' + mid.replace('.', '/') + '.olean' in compiled, 'Missing warm module.')
        write_new(output / 'warm-compiled-artifacts.json', encode(compiled))
        receipt.update(package_heads=packages, compiled_artifacts_sha256=digest(encode(compiled)))
        profile = profile_module(workspace, output / 'profile', manifest, expected, packages, compiled, env, toolchain_bin, budget)
        receipt['profile'] = profile
        library = Path(profile['diagnostic_library'])
        overlay = overlay_dependencies(workspace, library, compiled, manifest, profile['fresh_artifacts'])
        write_new(output / 'overlay-artifacts.json', encode(overlay))
        receipt['overlay_artifacts_sha256'] = profile['overlay_artifacts_sha256'] = digest(encode(overlay))
        (output / 'profile/result.json').write_bytes(encode(profile))
        verify_declaration_trace(workspace, profile['declaration_trace'])
        receipt['post_check'] = post_check_profile(workspace, output / 'post-check', driver, manifest, expected, packages,
                                                  compiled, env, toolchain_bin, library, profile['fresh_artifacts'], overlay, budget)
        verify_seals(workspace, manifest, expected, packages, compiled, env, budget)
        verify_library(workspace, library, profile['fresh_artifacts'], overlay)
        verify_declaration_trace(workspace, profile['declaration_trace'])
        receipt['status'] = 'completed'
    except Exception as error:
        receipt.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        files = {}
        for path in output.rglob('*'):
            core.path_checked(path)
            if path.is_dir() or path == output / 'receipt.json':
                continue
            files[path.relative_to(output).as_posix()] = digest(core.regular(path).read_bytes())
        receipt['files_sha256'] = files
        (output / 'receipt.json').write_bytes(encode(receipt))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['validate', 'run'])
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--config-sha256', required=True)
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.action == 'validate':
        load_config(args.config, args.config_sha256)
        print('Exact baseline-only profile bindings validated; no execution performed.')
    else:
        require(args.workspace is not None and args.output is not None, 'Fresh workspace/output paths required.')
        run(args.config, args.config_sha256, args.workspace, args.output)


if __name__ == '__main__':
    main()
