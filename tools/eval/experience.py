#!/usr/bin/env python3
"""逐键、选词、翻页与跨会话学习的离线体验评分；发布前必须通过冻结基线。"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SEEDS = ROOT / 'assets/eval/experience/scenarios.json'
REFERENCE = ROOT / 'assets/eval/experience/reference.json'
PRODUCT_FILES = ['data/generated/dict.qj', 'data/generated/dicts/general.qj',
                 'data/generated/lm.qj', 'data/generated/english.tsv',
                 'assets/lexicon/patches.tsv', 'assets/lexicon/supplement/dict.tsv']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


def summarize(rows, checks):
    count = len(rows)
    top1 = sum(r['position'] == 0 for r in rows) / count
    top5 = sum(r['position'] is not None and r['position'] < 5 for r in rows) / count
    completion = sum(r['completed'] for r in rows) / count
    # 失败任务计零，不能靠放弃难题降低翻页数或提高效率。
    efficiency = sum(min(1, (len(r['keys']) + 1) / r['actions']) if r['completed'] else 0 for r in rows) / count
    learning = sum(c['passed'] for c in checks) / len(checks)
    stability = sum(r['stable'] for r in rows) / count
    latencies = [t for r in rows for t in r['query_ms']]
    p95 = percentile(latencies, .95)
    parts = dict(top1=30 * top1, top5=10 * top5, completion=15 * completion,
                 efficiency=10 * efficiency, interactions=20 * learning,
                 stability=10 * stability, response=5 * min(1, 10 / max(.001, p95)))
    return dict(count=count, top1=top1, top5=top5, completion=completion,
                efficiency=efficiency, interactions=learning, stability=stability,
                total_page_turns=sum(r['page_turns'] for r in rows),
                total_actions=sum(r['actions'] for r in rows),
                query_p50_ms=percentile(latencies, .5), query_p95_ms=p95,
                query_p99_ms=percentile(latencies, .99), query_max_ms=max(latencies),
                score=round(sum(parts.values()), 2), score_parts=parts)


def validate(report, seeds):
    assert report['schema'] == 1 and report['network'] is False
    rows = report['results']
    assert len(rows) == len(seeds) and len({r['id'] for r in rows}) == len(rows), 'incomplete replay'
    for seed, row in zip(seeds, rows):
        assert all(row[key] == seed[key] for key in ['id', 'scene', 'text', 'keys'])
        target = seed['text'].rstrip('，？')
        assert row['position'] == next((i for i, t in enumerate(row['candidates']) if t == target), None)
        assert row['top'] == next(iter(row['candidates']), None)
        assert row['completed'] == (row['output'] == row['text'] and row['remaining_keys'] == '')
        assert row['actions'] > 0 and row['query_ms'] and row['prefixes']
        assert all(math.isfinite(t) and t >= 0 for t in row['query_ms'])
    expected = {'same-input-learning', 'reload-learning', 'private-input', 'learning-disabled',
                'replace-wrong-selection', 'raw-enter', 'backspace-edit',
                'switch-input-box', 'discard-private-composition'}
    assert {c['id'] for c in report['checks']} == expected and len(report['checks']) == len(expected)


def compare(rows, previous):
    assert len(rows) == len(previous['results']), 'different baseline size'
    failures = []
    for before, after in zip(previous['results'], rows):
        assert (before['id'], before['text'], before['keys']) == (after['id'], after['text'], after['keys'])
        for k in [1, 5]:
            if before['position'] is not None and before['position'] < k:
                if after['position'] is None or after['position'] >= k:
                    failures.append(dict(id=after['id'], metric=f'top{k}'))
        if before['completed'] and not after['completed']:
            failures.append(dict(id=after['id'], metric='completion'))
    return failures


def run(binary, output, reference=REFERENCE, all_candidates=False, word_limit=None):
    binary = binary.resolve()
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ)
    for key in ['QINGJIAN_API_KEY', 'OPENAI_API_KEY', 'QINGJIAN_LOG_DIR']:
        env.pop(key, None)
    command = [str(binary), '--experience', str((output / 'replay.json').resolve())]
    if all_candidates:
        command += ['--experience-all']
    if word_limit is not None:
        command += ['--experience-word-limit', str(word_limit)]
    fingerprint = sha(binary)
    with (output / 'replay.log').open('w', encoding='utf-8') as log:
        subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=600)
    assert sha(binary) == fingerprint, 'binary changed during replay'
    replay = json.loads((output / 'replay.json').read_text(encoding='utf-8'))
    validate(replay, json.loads(SEEDS.read_text(encoding='utf-8')))
    rows = replay['results']
    report = dict(schema=1, mode=replay['mode'], word_limit=replay['word_limit'], binary_sha256=fingerprint,
                  product_data_sha256={name: sha(ROOT / name) for name in PRODUCT_FILES},
                  seed_sha256=sha(SEEDS), data_lock_sha256=sha(ROOT / 'tools/release/data.lock'),
                  dictionary_sha256=sha(ROOT / 'data/generated/dict.qj'),
                  supplement_sha256=sha(ROOT / 'assets/lexicon/supplement/dict.tsv'),
                  source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  source_dirty=bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
                  **summarize(rows, replay['checks']))
    report['scenes'] = {scene: summarize([r for r in rows if r['scene'] == scene], replay['checks'])
                        for scene in sorted({r['scene'] for r in rows})}
    failures = [dict(id=c['id'], metric='interaction') for c in replay['checks'] if not c['passed']]
    if reference:
        previous = json.loads(reference.read_text(encoding='utf-8'))
        for key in ['seed_sha256', 'data_lock_sha256', 'dictionary_sha256', 'supplement_sha256', 'product_data_sha256']:
            assert previous[key] == report[key], f'baseline fingerprint differs: {key}'
        failures += compare(rows, previous)
        if report['total_actions'] > previous['total_actions'] * 1.05:
            failures.append(dict(id='aggregate', metric='actions'))
    failures += [dict(id=r['id'], metric='stability') for r in rows if not r['stable']]
    # 给不同编译机留余量；评分的 10ms 目标更严格，门禁先拦住明显的交互卡顿。
    if report['query_p95_ms'] > 50 or report['query_max_ms'] > 1000:
        failures.append(dict(id='aggregate', metric='response'))
    report['regressions'] = failures
    report['status'] = 'passed' if not failures else 'failed'
    baseline = {key: report[key] for key in ['seed_sha256', 'data_lock_sha256',
                                           'dictionary_sha256', 'supplement_sha256', 'product_data_sha256', 'total_actions']}
    baseline['results'] = [{k: r[k] for k in ['id', 'text', 'keys', 'position', 'completed']} for r in rows]
    for name, data in [('summary.json', report), ('reference.json', baseline)]:
        (output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['count', 'mode', 'score', 'top1', 'top5', 'completion',
                                          'total_actions', 'total_page_turns', 'query_p95_ms', 'status', 'regressions']},
                     ensure_ascii=False, indent=2))
    assert not failures, 'experience regression; inspect summary.json and replay.json'
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reference', type=Path, default=REFERENCE)
    parser.add_argument('--all', action='store_true', help='回放旧的无限整词浏览')
    parser.add_argument('--word-limit', type=int, help='比较普通整词额度，不改产品配置')
    parser.add_argument('--baseline', action='store_true', help='仅生成隔离基线，不覆盖仓库基线')
    args = parser.parse_args()
    run(args.binary, args.output, None if args.baseline else args.reference, args.all, args.word_limit)
