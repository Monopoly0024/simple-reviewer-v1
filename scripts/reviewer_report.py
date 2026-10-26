#!/usr/bin/env python3
"""Validate review evidence and render a local report; never execute recorded commands."""

import argparse
import base64
import copy
from datetime import datetime
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sys
import textwrap
from urllib.parse import quote


LABELS = {'passed': '已验证通过', 'failed': '已确认问题',
          'pending': '待核实', 'unchecked': '未验证'}
COLORS = {'passed': ('#dcfce7', '#15803d', '#14532d'),
          'failed': ('#fee2e2', '#b91c1c', '#7f1d1d'),
          'pending': ('#fef3c7', '#a16207', '#713f12'),
          'unchecked': ('#f3f4f6', '#6b7280', '#374151')}


def report_theme():
    """Embed the licensed font so each report stays usable offline."""
    assets = Path(__file__).resolve().parent.parent / 'assets'
    font = base64.b64encode((assets / 'fonts' / 'AlbertSans-VariableFont_wght.woff2').read_bytes()).decode('ascii')
    face = ('@font-face{font-family:"Albert Sans";font-style:normal;font-weight:100 900;'
            f'font-display:swap;src:url(data:font/woff2;base64,{font}) format("woff2");}}\n')
    return face + (assets / 'reviewer-theme.css').read_text(encoding='utf-8')


def document_previews(data):
    """Show real block summaries in the source reference's three-document layout."""
    cards = []
    for block in data['blocks'][:3]:
        state = block['status']
        cards.append('<article class="document-card"><div class="document-head"><span>代码职责 / '
                     + html.escape(block['id']) + '</span><b>' + html.escape(block['id'])
                     + '</b></div><div class="document-body"><p><small>block:</small> <mark>'
                     + html.escape(block['title']) + '</mark></p><p><b>作用</b><br>'
                     + html.escape(block['purpose']) + '</p><p><span class="badge ' + state + '">'
                     + LABELS[state] + '</span></p><p><small>预览来自下方真实板块记录。</small></p></div></article>')
    return '<div class="document-stack" aria-label="代码板块预览">' + ''.join(cards) + '</div>'


def optional_context(data):
    """Validate beginner-facing context without allowing it to alter evidence status."""
    context = {}
    goal = data.get('user_goal')
    if 'user_goal' in data:
        need(isinstance(goal, dict), 'user_goal must be an object')
        for key in ('original_request', 'plain_language'):
            if key in goal:
                need(isinstance(goal[key], str), f'user_goal.{key} must be text')
        for key in ('acceptance_criteria', 'assumptions', 'open_questions'):
            if key in goal:
                need(isinstance(goal[key], list) and all(isinstance(item, str) for item in goal[key]),
                     f'user_goal.{key} must be a text array')
        context['user_goal'] = goal
    changes = data.get('change_summary')
    if 'change_summary' in data:
        need(isinstance(changes, dict), 'change_summary must be an object')
        if 'baseline' in changes:
            need(isinstance(changes['baseline'], str), 'change_summary.baseline must be text')
        for key in ('files_added', 'files_modified', 'files_deleted', 'user_visible_changes', 'possible_impacts'):
            if key in changes:
                need(isinstance(changes[key], list) and all(isinstance(item, str) for item in changes[key]),
                     f'change_summary.{key} must be a text array')
        for key in ('files_added', 'files_modified', 'files_deleted'):
            for path in changes.get(key, []):
                project_path(Path(data['project_root']), path)
        context['change_summary'] = changes
    risks = data.get('risks')
    if 'risks' in data:
        need(isinstance(risks, list), 'risks must be an array')
        for index, risk in enumerate(risks, 1):
            need(isinstance(risk, dict), f'risks[{index}] must be an object')
            text_fields(risk, ('title', 'action', 'status', 'impact', 'next_step'), f'risks[{index}]')
            need(risk.get('status') in ('observed', 'not-run', 'mitigated', 'unknown'),
                 f'risks[{index}].status is invalid')
        context['risks'] = risks
    actions = data.get('next_actions')
    if 'next_actions' in data:
        need(isinstance(actions, list), 'next_actions must be an array')
        for index, action in enumerate(actions, 1):
            need(isinstance(action, dict), f'next_actions[{index}] must be an object')
            text_fields(action, ('action', 'reason'), f'next_actions[{index}]')
        context['next_actions'] = actions
    comprehension = data.get('comprehension')
    if 'comprehension' in data:
        need(isinstance(comprehension, dict), 'comprehension must be an object')
        glossary = comprehension.get('glossary', [])
        need(isinstance(glossary, list), 'comprehension.glossary must be an array')
        for index, item in enumerate(glossary, 1):
            need(isinstance(item, dict), f'comprehension.glossary[{index}] must be an object')
            text_fields(item, ('term', 'meaning'), f'comprehension.glossary[{index}]')
        context['comprehension'] = comprehension
    data['context'] = context
    return context


def need(condition, message):
    if not condition:
        raise ValueError(message)


def text_fields(item, fields, context):
    for field in fields:
        need(isinstance(item.get(field), str) and item[field].strip(), f'{context}: missing {field}')


def project_path(root, value):
    need(isinstance(value, str) and bool(value.strip()), 'Empty project path')
    path = Path(value)
    need(not path.is_absolute() and '..' not in path.parts, f'Path outside project: {value}')
    target = (root / path).resolve()
    need(target.is_relative_to(root), f'Path outside project: {value}')
    return target


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def indexed(items, prefix):
    need(isinstance(items, list), f'{prefix}: expected an array')
    result = {}
    for item in items:
        need(isinstance(item, dict), f'{prefix}: expected object')
        key = item.get('id', '')
        need(isinstance(key, str) and re.fullmatch(prefix + r'[1-9][0-9]*', key), f'Invalid ID: {key}')
        need(key not in result, f'Duplicate ID: {key}')
        result[key] = item
    return result


def refs(item, field, index):
    values = item.get(field, [])
    need(isinstance(values, list), f'{item.get("id", "edge")}: {field} must be array')
    need(all(isinstance(key, str) and key in index for key in values),
         f'{item.get("id", "edge")}: unknown {field}')
    return [index[key] for key in values]


def assess(record, record_dir):
    """Return an independent effective snapshot, downgrading stale evidence."""
    data = copy.deepcopy(record)
    need(data.get('schema_version') == '1.0', 'Expected schema_version 1.0')
    text_fields(data, ['title', 'reviewed_at', 'project_root'], 'review')
    try:
        when = datetime.fromisoformat(data['reviewed_at'])
        need(when.utcoffset() is not None, 'reviewed_at requires a timezone')
    except (ValueError, TypeError) as exc:
        raise ValueError(f'Invalid reviewed_at: {exc}') from exc
    need(data.get('mode') in ('review', 'review-and-fix'), 'Invalid review mode')
    root_value = Path(data['project_root'])
    root = (root_value if root_value.is_absolute() else Path(record_dir) / root_value).resolve()
    need(root.is_dir(), f'Project root not found: {root}')
    data['project_root'] = str(root)
    optional_context(data)
    snapshot = data.get('snapshot', {})
    text_fields(snapshot, ['base_revision', 'notes'], 'snapshot')
    need(isinstance(snapshot.get('files'), list), 'snapshot.files must be an array')
    files = {}
    stale_files = set()
    for entry in snapshot['files']:
        text_fields(entry, ['path', 'sha256'], 'snapshot file')
        path = project_path(root, entry['path'])
        need(entry['path'] not in files, f'Duplicate snapshot path: {entry["path"]}')
        need(bool(re.fullmatch('[0-9a-fA-F]{64}', entry['sha256'])), 'Invalid source SHA-256')
        files[entry['path']] = path
        if not path.is_file() or digest(path) != entry['sha256'].lower():
            stale_files.add(entry['path'])
    requirements = indexed(data.get('requirements'), 'R')
    nodes = indexed(data.get('nodes'), 'N')
    issues = indexed(data.get('issues'), 'I')
    evidence = indexed(data.get('evidence'), 'E')
    need(bool(nodes), 'At least one node is required')
    stale_evidence = set()
    for check in evidence.values():
        key = check['id']
        text_fields(check, ['command', 'cwd', 'expected', 'observed', 'scope'], key)
        need(check.get('kind') in ('runtime', 'static'), f'{key}: invalid kind')
        need(check.get('outcome') in ('passed', 'failed', 'blocked'), f'{key}: invalid outcome')
        source_files = check.get('source_files')
        need(isinstance(source_files, list) and bool(source_files), f'{key}: source_files required')
        need(all(isinstance(name, str) and name in files for name in source_files),
             f'{key}: source_files not in snapshot')
        project_path(root, check['cwd'])
        stale = bool(stale_files.intersection(source_files))
        if check['kind'] == 'runtime':
            text_fields(check, ['log_path', 'log_sha256'], key)
            need(type(check.get('exit_code')) is int, f'{key}: runtime exit_code required')
            need(bool(re.fullmatch('[0-9a-fA-F]{64}', check['log_sha256'])), f'{key}: invalid log SHA-256')
            log = project_path(root, check['log_path'])
            stale = stale or not log.is_file() or digest(log) != check['log_sha256'].lower()
            if check['outcome'] == 'passed':
                need(check['exit_code'] == 0, f'{key}: passed runtime has nonzero exit code')
        if stale:
            stale_evidence.add(key)
    for issue in issues.values():
        text_fields(issue, ['title', 'impact', 'suggestion'], issue['id'])
        need(issue.get('status') in ('confirmed', 'suspected'), 'Invalid issue status')
        need(issue.get('severity') in ('blocking', 'nonblocking'), 'Invalid severity')
        refs(issue, 'node_ids', nodes)
        checks = refs(issue, 'evidence_ids', evidence)
        need(bool(issue.get('node_ids')), f'{issue["id"]}: node_ids required')
        if issue['status'] == 'confirmed':
            need(any(check['outcome'] == 'failed' for check in checks),
                 f'{issue["id"]}: confirmed issue requires failed evidence')
        issue['stale'] = bool(stale_evidence.intersection(issue.get('evidence_ids', [])))
    for node in nodes.values():
        key = node['id']
        text_fields(node, ['title', 'expected', 'actual', 'input', 'output', 'scope', 'reason'], key)
        need(node.get('status') in LABELS, f'{key}: invalid status')
        need(node.get('role') in ('implemented', 'missing', 'unprovided'), f'{key}: invalid role')
        refs(node, 'requirement_ids', requirements)
        refs(node, 'affected_by', nodes)
        checks = refs(node, 'evidence_ids', evidence)
        linked_issues = refs(node, 'issue_ids', issues)
        need(isinstance(node.get('locations'), list), f'{key}: locations required')
        for loc in node['locations']:
            need(loc.get('path') in files, f'{key}: location outside snapshot')
            need(type(loc.get('line')) is int and loc['line'] > 0, f'{key}: invalid source line')
            if 'end_line' in loc:
                need(type(loc['end_line']) is int and loc['end_line'] >= loc['line'],
                     f'{key}: invalid source line range')
            if 'symbol' in loc:
                text_fields(loc, ['symbol'], key)
        if node['status'] == 'passed':
            need(any(c['kind'] == 'runtime' and c['outcome'] == 'passed' for c in checks),
                 f'{key}: green node requires passed runtime evidence')
            need(not any(c['outcome'] == 'failed' and c['id'] not in stale_evidence for c in checks),
                 f'{key}: active failed evidence conflicts with green status')
            need(not linked_issues, f'{key}: green node still has unresolved issues')
        if node['status'] == 'failed':
            need(any(c['outcome'] == 'failed' for c in checks), f'{key}: failed evidence required')
            need(any(i['status'] == 'confirmed' for i in linked_issues), f'{key}: confirmed issue required')
        if node['role'] == 'missing':
            need(node['status'] == 'failed', f'{key}: missing node requires confirmed failure')
        if node['role'] == 'unprovided':
            need(node['status'] in ('pending', 'unchecked'), f'{key}: unprovided node cannot be verified')
    for requirement in requirements.values():
        key = requirement['id']
        text_fields(requirement, ['text', 'source', 'acceptance'], key)
        need(type(requirement.get('required')) is bool, f'{key}: required must be boolean')
        need(requirement.get('status') in ('passed', 'failed', 'unchecked'), f'{key}: invalid status')
        linked_nodes = refs(requirement, 'node_ids', nodes)
        checks = refs(requirement, 'evidence_ids', evidence)
        if requirement['status'] == 'passed':
            need(bool(linked_nodes) and all(n['status'] == 'passed' for n in linked_nodes),
                 f'{key}: passed requirement has unverified node')
            need(any(c['kind'] == 'runtime' and c['outcome'] == 'passed' for c in checks),
                 f'{key}: passed requirement requires runtime evidence')
            need(not any(c['outcome'] == 'failed' and c['id'] not in stale_evidence for c in checks),
                 f'{key}: active failed evidence conflicts with passed requirement')
        if requirement['status'] == 'failed':
            need(any(c['outcome'] == 'failed' for c in checks), f'{key}: failed evidence required')
    need(isinstance(data.get('edges'), list), 'edges must be an array')
    for edge in data['edges']:
        need(edge.get('source') in nodes and edge.get('target') in nodes, 'Unknown edge node')
        need(edge.get('kind') in ('normal', 'exception', 'affected', 'inferred'), 'Invalid edge kind')
        need(isinstance(edge.get('label'), str), 'Edge label required')
        refs(edge, 'issue_ids', issues)
    for node in nodes.values():
        own_changed = any(loc['path'] in stale_files for loc in node['locations'])
        if own_changed or stale_evidence.intersection(node.get('evidence_ids', [])):
            node['reported_status'] = node['status']
            node['status'] = 'pending'
            node['reason'] = '源文件或证据日志变化，待重新验证。原记录：' + node['reason']
    for requirement in requirements.values():
        linked_nodes = refs(requirement, 'node_ids', nodes)
        if stale_evidence.intersection(requirement.get('evidence_ids', [])) or any('reported_status' in n for n in linked_nodes):
            requirement['reported_status'] = requirement['status']
            requirement['status'] = 'unchecked'
    if 'blocks' not in data:
        data['blocks'] = [{'id': f'B{number}', 'title': node['title'],
                           'purpose': node['expected'], 'node_ids': [node['id']]}
                          for number, node in enumerate(nodes.values(), 1)]
        data['block_grouping'] = '未提供板块分组，按已有职责节点生成；整体划分仍需审查者确认。'
    else:
        data['block_grouping'] = '按审查者提供的功能板块分组；板块结论由当前有效节点状态汇总。'
    blocks = indexed(data['blocks'], 'B')
    membership = []
    for block in blocks.values():
        text_fields(block, ['title', 'purpose'], block['id'])
        if 'explanation' in block:
            explanation = block['explanation']
            need(isinstance(explanation, dict), f'{block["id"]}: explanation must be object')
            if 'summary' in explanation:
                text_fields(explanation, ['summary'], block['id'])
            if 'steps' in explanation:
                steps = explanation['steps']
                need(isinstance(steps, list) and 1 <= len(steps) <= 12,
                     f'{block["id"]}: steps must contain 1..12 objects')
                for step in steps:
                    need(isinstance(step, dict), f'{block["id"]}: invalid step')
                    text_fields(step, ['title', 'detail'], block['id'])
            if 'example' in explanation:
                example = explanation['example']
                need(isinstance(example, dict), f'{block["id"]}: example must be object')
                text_fields(example, ['input', 'expected', 'note'], block['id'])
        members = refs(block, 'node_ids', nodes)
        need(bool(members), f'{block["id"]}: block must contain nodes')
        membership.extend(block['node_ids'])
        states = {node['status'] for node in members}
        block['status'] = next(state for state in ('failed', 'pending', 'unchecked', 'passed') if state in states)
    need(len(membership) == len(set(membership)), 'A node belongs to multiple blocks')
    need(set(membership) == set(nodes), 'Blocks must cover all reviewed nodes')
    active_blocking = any(i['severity'] == 'blocking' and i['status'] == 'confirmed' and not i['stale']
                          for i in issues.values())
    required = [r for r in requirements.values() if r['required']]
    if active_blocking or any(r['status'] == 'failed' for r in required):
        overall = 'failed'
    elif (required and all(r['status'] == 'passed' for r in required)
          and not any(q.strip() for q in data.get('user_goal', {}).get('open_questions', []))):
        overall = 'passed'
    else:
        overall = 'unchecked'
    data.update(overall=overall, stale_files=sorted(stale_files), stale_evidence=sorted(stale_evidence))
    return data


def context_sections(data):
    """Return shared, escaped HTML and readable Markdown from effective review data."""
    esc = lambda value: html.escape(str(value), quote=True)
    sections, lines = [], []

    def section(key, title, body, text):
        sections.append(f'<section class="context-section" id="{key}"><h2>{title}</h2>{body}</section>')
        lines.extend([f'## {title}', '', *text, ''])

    def listing(values, empty):
        return ('<ul>' + ''.join(f'<li>{esc(value)}</li>' for value in values) + '</ul>'
                if values else f'<p class="muted">{empty}</p>')

    goal = data.get('user_goal', {})
    goal_body = '<p class="original-request">' + esc(goal.get('original_request') or '未提供原始需求原文；以下验收项来自审查记录。') + '</p>'
    goal_text = [goal.get('original_request') or '未提供原始需求原文；以下验收项来自审查记录。']
    if goal.get('plain_language'):
        goal_body += '<p>' + esc(goal['plain_language']) + '</p>'
        goal_text += ['', goal['plain_language']]
    for key, label in [('acceptance_criteria', '补充验收描述（有效状态以下方验收项为准）'),
                       ('assumptions', '仍属假设'), ('open_questions', '需要明确的问题')]:
        if goal.get(key):
            goal_body += f'<h3>{label}</h3>' + listing(goal[key], '')
            goal_text += ['', label + '：', *['- ' + item for item in goal[key]]]
    section('goal', '我想要什么', goal_body, goal_text)

    changes = data.get('change_summary')
    change_body, change_text = '', []
    if not changes:
        change_body = '<p class="muted">未登记变更说明；不能仅凭当前源码判断 AI 刚刚改了哪些内容。</p>'
        change_text = ['未登记变更说明；不能仅凭当前源码判断 AI 刚刚改了哪些内容。']
    else:
        baseline = changes.get('baseline') or '未提供可比较基线；以下为审查者登记的变更说明。'
        change_body = '<p class="muted">比较基线：' + esc(baseline) + '</p>'
        change_text = ['比较基线：' + baseline]
        for key, label in [('user_visible_changes', '你会看到的变化'), ('files_added', '新增文件'),
                           ('files_modified', '修改文件'), ('files_deleted', '删除文件'), ('possible_impacts', '可能影响')]:
            if changes.get(key):
                change_body += f'<h3>{label}</h3>' + listing(changes[key], '')
                change_text += ['', label + '：', *['- ' + item for item in changes[key]]]
    section('changes', 'AI 改了什么', change_body, change_text)

    checks = {e['id']: e for e in data['evidence']}
    matrix = ['<div class="acceptance-list">']
    matrix_text = ['| 目标 | 验收条件 | 实际观察及范围 | 有效状态 |', '| --- | --- | --- | --- |']
    for req in data['requirements']:
        observations = []
        for key in req['evidence_ids']:
            e = checks[key]
            stale = '证据已过期，待复验；' if key in data['stale_evidence'] else ''
            kind = '实际执行记录' if e['kind'] == 'runtime' else '静态核对'
            observations.append(f'{key} · {kind} · {stale}{e["observed"]}；范围：{e["scope"]}')
        observed = '；'.join(observations) or '没有登记实际验证证据。'
        matrix.append(f'<article class="acceptance {req["status"]}"><div class="acceptance-heading"><h3>{esc(req["id"])} · {esc(req["text"])}</h3><span class="badge {req["status"]}">{LABELS[req["status"]]}</span></div>'
                      f'<p><b>怎样才算完成：</b>{esc(req["acceptance"])}</p><p><b>实际观察：</b>{esc(observed)}</p>'
                      f'<details><summary>查看需求来源与检查步骤</summary><p>{esc(req["source"])}</p>'
                      + ''.join(f'<p>{esc(checks[key]["command"])}<br>独立预期：{esc(checks[key]["expected"])}</p>' for key in req['evidence_ids'])
                      + '</details></article>')
        matrix_text.append('| ' + ' | '.join(md_cell(value) for value in [req['text'], req['acceptance'], observed, LABELS[req['status']]]) + ' |')
    matrix.append('</div>')
    if not data['requirements']:
        matrix.append('<p class="muted">未登记验收目标，无法给出目标完成结论。</p>')
    section('acceptance', '实际检查了什么', ''.join(matrix), matrix_text)

    risk_labels = {'observed': '动作已发生', 'not-run': '尚未执行', 'mitigated': '已登记缓解措施', 'unknown': '执行状态待确认'}
    risks = data.get('risks', [])
    risk_body, risk_text = [], []
    for risk in risks:
        risk_body.append('<article class="risk-card"><h3>' + esc(risk['title']) + '</h3><span class="risk-state">'
                         + risk_labels[risk['status']] + '</span><p><b>涉及动作：</b>' + esc(risk['action'])
                         + '</p><p><b>影响：</b>' + esc(risk['impact']) + '</p><p><b>处理建议：</b>' + esc(risk['next_step']) + '</p></article>')
        risk_text += [f'### {risk["title"]} · {risk_labels[risk["status"]]}', '',
                      '涉及动作：' + risk['action'], '', '影响：' + risk['impact'], '', '处理建议：' + risk['next_step'], '']
    if not risks:
        risk_body = ['<p class="muted">未登记风险检查；这不表示没有风险。</p>']
        risk_text = ['未登记风险检查；这不表示没有风险。']
    section('risks', '需要留意的影响', ''.join(risk_body), risk_text)

    actions = data.get('next_actions', [])
    action_body = ''.join('<li><strong>' + esc(a['action']) + '</strong><p>' + esc(a['reason']) + '</p></li>' for a in actions)
    section('next-actions', '下一步怎么做', '<ol class="action-list">' + action_body + '</ol>' if actions else
            '<p class="muted">未登记下一步。可从未验证目标或已确认问题继续询问，先补证据再作结论。</p>',
            [f'{i}. {a["action"]} — {a["reason"]}' for i, a in enumerate(actions, 1)] or ['未登记下一步；先明确未验证目标和证据缺口。'])
    glossary = data.get('comprehension', {}).get('glossary', [])
    if glossary:
        section('glossary', '读不懂的词，点开看', ''.join('<details><summary>' + esc(item['term']) + '</summary><p>'
                + esc(item['meaning']) + '</p></details>' for item in glossary), ['- ' + item['term'] + '：' + item['meaning'] for item in glossary])
    return ''.join(sections), '\n'.join(lines)


def mermaid(data):
    lines = ['flowchart TD']
    for node in data['nodes']:
        label = f'{node["id"]} {node["title"]}<br/>{LABELS[node["status"]]}'
        label = label.replace('"', '#quot;').replace('[', '#91;').replace(']', '#93;')
        label = label.replace('\r', ' ').replace('\n', ' ').replace('`', '#96;')
        lines.append(f'    {node["id"]}["{label}"]')
    for edge in data['edges']:
        label = html.escape(edge['label']).replace('|', '#124;').replace('\n', ' ')
        arrow = '-->' if edge['kind'] == 'normal' else '-.->'
        lines.append(f'    {edge["source"]} {arrow}{"|" + label + "|" if label else ""} {edge["target"]}')
    for status, (fill, stroke, color) in COLORS.items():
        lines.append(f'    classDef {status} fill:{fill},stroke:{stroke},color:{color};')
        ids = ','.join(n['id'] for n in data['nodes'] if n['status'] == status)
        if ids:
            lines.append(f'    class {ids} {status};')
    for node in data['nodes']:
        if node['role'] == 'missing':
            lines.append(f'    style {node["id"]} stroke-dasharray: 5 4;')
    issue_index = {i['id']: i for i in data['issues']}
    for index, edge in enumerate(data['edges']):
        linked = [issue_index[i] for i in edge.get('issue_ids', [])]
        if linked:
            color = '#b91c1c' if any(i['status'] == 'confirmed' and not i['stale'] for i in linked) else '#a16207'
            lines.append(f'    linkStyle {index} stroke:{color},stroke-width:2px;')
    return '\n'.join(lines)


def md_cell(value):
    return str(value).replace('|', '\\|').replace('\n', '<br/>')


def source_location(data, location):
    """Keep line extent readable while linking to a verified absolute start line."""
    path = project_path(Path(data['project_root']), location['path'])
    label = f'{location["path"]}:{location["line"]}'
    if location.get('end_line', location['line']) > location['line']:
        label += f'–{location["end_line"]}'
    if location.get('symbol'):
        label += f' · {location["symbol"]}'
    label = html.escape(label).replace('[', '&#91;').replace(']', '&#93;')
    target = path.as_posix().replace('<', '%3C').replace('>', '%3E')
    return f'[{label}](<{target}:{location["line"]}>)'


def block_graph(data):
    lookup = {node: block['id'] for block in data['blocks'] for node in block['node_ids']}
    nodes = [{'id': b['id'], 'title': b['title'], 'status': b['status'], 'role': 'implemented'}
             for b in data['blocks']]
    edges = []
    seen = set()
    for edge in data['edges']:
        start, end = lookup[edge['source']], lookup[edge['target']]
        key = (start, end, edge['kind'], edge['label'])
        if start != end and key not in seen:
            edges.append({**edge, 'source': start, 'target': end})
            seen.add(key)
    return mermaid({'nodes': nodes, 'edges': edges, 'issues': data['issues']})


def code_breakdown(data):
    """A self-contained code map with per-block behavior evidence, not just a finding list."""
    node_index = {n['id']: n for n in data['nodes']}
    requirement_index = {r['id']: r for r in data['requirements']}
    issue_index = {i['id']: i for i in data['issues']}
    effect = {'passed': '已验证生效（仅限下述验证范围）',
              'failed': '未达到预期作用（已确认问题，见失败证据）',
              'pending': '作用是否生效仍待核实',
              'unchecked': '尚未验证作用是否生效'}
    lines = [f'# 代码拆解说明 · {data["title"]}', '',
             f'审查时间：{data["reviewed_at"]}；项目根目录：`{data["project_root"]}`。', '',
             f'基线：{data["snapshot"]["base_revision"]}。{data["snapshot"]["notes"]}', '',
             '## 整体划分与阅读范围', '', data['block_grouping'], '',
             data.get('journey_note', '整体运行路径的覆盖范围，以各节点的验证证据为准。'), '',
             '本文件逐块解释职责、实际行为、代码位置与生效证据。它是独立交付文件，无需打开总审查报告。', '',
             '颜色：绿色=已验证通过，红色=已确认问题，黄色=待核实，灰色=未验证。板块颜色按包含节点汇总，正常子节点仍保留自身状态；局部通过不表示整体流程已完成。', '',
             context_sections(data)[1], '',
             '```mermaid', block_graph(data), '```', '',
             '| 板块 | 作用 | 作用验证 | 代码位置 |', '| --- | --- | --- | --- |']
    for block in data['blocks']:
        locations = list(dict.fromkeys(source_location(data, loc)
            for key in block['node_ids'] for loc in node_index[key]['locations']))
        lines.append('| ' + ' | '.join(md_cell(value) for value in (
            f'{block["id"]} {block["title"]}', block['purpose'], effect[block['status']],
            '<br/>'.join(locations) or '未提供实现或位置，不能伪造代码位置')) + ' |')
    for block in data['blocks']:
        members = [node_index[key] for key in block['node_ids']]
        lines += ['', f'## {block["id"]} {block["title"]}', '',
                  f'板块职责：{block["purpose"]}', '', f'作用是否生效：**{effect[block["status"]]}**。', '']
        boundary = [edge for edge in data['edges']
                    if (edge['source'] in block['node_ids']) != (edge['target'] in block['node_ids'])]
        if boundary:
            lines += ['上下游关系：', '']
            for edge in boundary:
                lines.append(f'- {edge["source"]} {node_index[edge["source"]]["title"]} → '
                             f'{edge["target"]} {node_index[edge["target"]]["title"]}：'
                             f'{edge["label"] or "调用或数据传递"}（{edge["kind"]}）。')
            lines += ['']
        else:
            lines += ['上下游关系：未登记跨板块连接；不能据此认定已接入完整流程。', '']
        for node in members:
            lines += [f'### {node["id"]} {node["title"]} · {LABELS[node["status"]]}', '',
                      f'- 应有作用：{node["expected"]}', f'- 实际行为：{node["actual"]}',
                      f'- 输入：{node["input"]}', f'- 输出：{node["output"]}',
                      '- 代码位置：' + ('；'.join(source_location(data, loc) for loc in node['locations'])
                                       or '未提供实现或位置，不能伪造代码位置'),
                      f'- 作用验证：{effect[node["status"]]}。{node["reason"]}',
                      f'- 验证范围与限制：{node["scope"]}']
            for key in node['requirement_ids']:
                req = requirement_index[key]
                lines.append(f'- 对应需求 {key}：{req["text"]}；验收：{req["acceptance"]}；来源：{req["source"]}。')
            if node.get('affected_by'):
                lines.append('- 受上游影响：' + '、'.join(node['affected_by']) + '；独立检查状态不代表完整结果正确。')
            for key in node['issue_ids']:
                issue = issue_index[key]
                state = '旧证据已过期，待复验' if issue['stale'] else issue['status']
                lines.append(f'- 问题 {key}：{issue["title"]}（{state}，{issue["severity"]}）；'
                             f'影响：{issue["impact"]}；建议：{issue["suggestion"]}。')
            if not node['evidence_ids']:
                lines.append('- 尚无验证证据；后续需执行能观察该职责结果的检查。')
            lines += ['']
        checks = list(dict.fromkeys(key for node in members for key in node['evidence_ids']))
        if checks:
            lines += ['### 本板块验证证据', '']
        for check in data['evidence']:
            if check['id'] not in checks:
                continue
            stale = '（已过期，不能作为当前生效证明）' if check['id'] in data['stale_evidence'] else ''
            lines += [f'**{check["id"]} · {check["kind"]} / {check["outcome"]}** {stale}', '',
                      f'- 命令或操作：{check["command"]}', f'- 工作目录：{check["cwd"]}；退出码：{check.get("exit_code")}',
                      f'- 独立预期：{check["expected"]}', f'- 实际观察：{check["observed"]}',
                      f'- 覆盖范围：{check["scope"]}',
                      f'- 日志：{check.get("log_path", "仅静态检查，无运行日志")}；SHA-256：{check.get("log_sha256", "不适用")}', '']
    mapped = {loc['path'] for node in data['nodes'] for loc in node['locations']}
    supporting = [f['path'] for f in data['snapshot']['files'] if f['path'] not in mapped]
    lines += ['## 位置索引与覆盖边界', '',
              '位置链接指向绝对文件及起始行；范围和符号仅在审查者提供时显示。位置对应审查快照，代码改动后需重新定位。', '',
              '登记为验证或关联依赖、未单独拆成板块的文件：' + ('、'.join(supporting) if supporting else '无。'), '',
              '本文件只覆盖上述审查范围，不声称已解释未提供或未审查的全部项目源码。未验证项需补充运行环境或有效证据；静态解释不证明运行生效。', '',
              '过期源文件：' + ('、'.join(data['stale_files']) or '无。'), '',
              '文件快照 SHA-256：', '']
    lines += [f'- `{entry["path"]}`：`{entry["sha256"]}`' for entry in data['snapshot']['files']]
    return '\n'.join(lines) + '\n'


def markdown(data):
    lines = [f'# {data["title"]}', '', f'总体结论：**{LABELS[data["overall"]]}**。', '', context_sections(data)[1], '',
             f'审查时间：{data["reviewed_at"]}；模式：{data["mode"]}。', '',
             f'项目：`{data["project_root"]}`', '', f'基线：{data["snapshot"]["base_revision"]}。{data["snapshot"]["notes"]}', '',
             data.get('journey_note', '完整路径范围：以各项证据的 scope 为准，未声明的路径不视为通过。'), '',
             '绿色=实际验证通过；红色=已确认问题；黄色=待核实；灰色=未验证。绿色只覆盖声明范围。', '',
             '```mermaid', mermaid(data), '```', '', '## 需求验收', '',
             '| 需求 | 验收条件 | 状态 | 节点 | 证据 |', '| --- | --- | --- | --- | --- |']
    for r in data['requirements']:
        lines.append('| ' + ' | '.join(md_cell(x) for x in [r['id'] + ' ' + r['text'], r['acceptance'],
                     LABELS[r['status']], ', '.join(r['node_ids']), ', '.join(r['evidence_ids'])]) + ' |')
    lines += ['', '## 节点说明', '']
    for node in data['nodes']:
        lines += [f'### {node["id"]} {node["title"]} — {LABELS[node["status"]]}', '',
                  f'- 应有作用：{node["expected"]}', f'- 实际行为：{node["actual"]}',
                  f'- 输入 → 输出：{node["input"]} → {node["output"]}',
                  '- 代码位置：' + ', '.join(f'`{p["path"]}:{p["line"]}`' for p in node['locations']),
                  f'- 验证范围：{node["scope"]}', f'- 状态依据：{node["reason"]}',
                  f'- 需求 / 证据 / 问题：{", ".join(node["requirement_ids"])} / {", ".join(node["evidence_ids"])} / {", ".join(node["issue_ids"])}', '']
    lines += ['## 问题与建议', '']
    if not data['issues']:
        lines += ['当前未登记已确认问题；这不代替未验证项的检查。', '']
    for issue in data['issues']:
        suffix = '（证据已过期，待复验）' if issue['stale'] else ''
        lines += [f'- **{issue["id"]} {issue["title"]}** — {issue["status"]}, {issue["severity"]}{suffix}',
                  f'  影响：{issue["impact"]}；建议：{issue["suggestion"]}；证据：{", ".join(issue["evidence_ids"])}。', '']
    lines += ['## 验证证据', '']
    for check in data['evidence']:
        stale = '；已过期' if check['id'] in data['stale_evidence'] else ''
        lines += [f'### {check["id"]} {check["kind"]} / {check["outcome"]}{stale}', '',
                  f'命令或操作：{check["command"]}', '', f'工作目录：{check["cwd"]}；退出码：{check.get("exit_code")}', '',
                  f'预期：{check["expected"]}', '', f'观察：{check["observed"]}', '', f'范围：{check["scope"]}', '',
                  f'日志：{check.get("log_path", "静态检查，无运行日志")}；哈希：{check.get("log_sha256", "不适用")}', '']
    lines += ['## 快照与限制', '', '```json', json.dumps(data['snapshot'], ensure_ascii=False, indent=2), '```', '',
              '这是一份时间点快照。文件变化后重新生成才能更新；生成器校验引用与哈希，不判断预期是否正确，也不会执行记录中的命令。', '']
    return '\n'.join(lines)


def graph_svg(data):
    nodes = data['nodes']
    normal = [e for e in data['edges'] if e['kind'] != 'affected']
    indegree = {n['id']: 0 for n in nodes}
    ranks = {n['id']: 0 for n in nodes}
    for edge in normal:
        indegree[edge['target']] += 1
    queue = [key for key in indegree if indegree[key] == 0]
    visited = set()
    while queue:
        key = queue.pop(0)
        visited.add(key)
        for edge in normal:
            if edge['source'] == key:
                target = edge['target']
                ranks[target] = max(ranks[target], ranks[key] + 1)
                indegree[target] -= 1
                if indegree[target] == 0:
                    queue.append(target)
    next_rank = max(ranks.values(), default=0) + 1
    for n in nodes:
        if n['id'] not in visited:
            ranks[n['id']] = next_rank
            next_rank += 1
    # Isolated/exception-only nodes get a distinct row instead of obscuring main paths.
    counts = {}
    positions = {}
    for node in nodes:
        rank = ranks[node['id']]
        col = counts.get(rank, 0)
        counts[rank] = col + 1
        positions[node['id']] = (36 + col * 278, 36 + rank * 134)
    width = max(x for x, _ in positions.values()) + 288
    height = max(y for _, y in positions.values()) + 122
    parts = [f'<svg viewBox="0 0 {width} {height}" style="max-width:{width}px;min-width:{width}px" role="group" aria-label="代码职责与验证状态流程图">',
             '<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="context-stroke"/></marker></defs>']
    issues = {i['id']: i for i in data['issues']}
    for index, edge in enumerate(data['edges']):
        sx, sy = positions[edge['source']]
        tx, ty = positions[edge['target']]
        linked = [issues[key] for key in edge.get('issue_ids', [])]
        color = '#64748b'
        if linked:
            color = '#b91c1c' if any(i['status'] == 'confirmed' and not i['stale'] for i in linked) else '#a16207'
        if ty > sy and tx == sx:
            path = f'M{sx + 120},{sy + 92} L{tx + 120},{ty - 4}'
            lx, ly = sx + 128, (sy + 92 + ty) / 2
        elif ty > sy:
            mid = (sy + 92 + ty) / 2
            path = f'M{sx + 120},{sy + 92} V{mid} H{tx + 120} V{ty - 4}'
            lx, ly = (sx + tx) / 2 + 120, mid - 7
        else:
            lane = min(sx, tx) - 13 - (index % 3) * 7
            path = f'M{sx},{sy + 46} H{lane} V{ty + 46} H{tx - 4}'
            lx, ly = lane + 4, (sy + ty) / 2 + 42
        dash = ' stroke-dasharray="5 4"' if edge['kind'] != 'normal' else ''
        label = html.escape(edge['label'])
        parts.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="1.7" marker-end="url(#arrow)"{dash}><title>{label}</title></path>')
        if label:
            parts.append(f'<text x="{lx}" y="{ly}" class="edge-label" fill="{color}">{label}</text>')
    for node in nodes:
        x, y = positions[node['id']]
        fill, stroke, color = COLORS[node['status']]
        label = html.escape(node['id'] + ' ' + node['title'])
        dash = ' stroke-dasharray="6 4"' if node['role'] == 'missing' else ''
        parts.append(f'<g class="node" role="button" tabindex="0" data-node="{node["id"]}" aria-label="{label}，{LABELS[node["status"]]}" aria-pressed="false">')
        parts.append(f'<rect x="{x}" y="{y}" width="240" height="92" rx="9" fill="{fill}" stroke="{stroke}" stroke-width="1.8"{dash}/>')
        for line_num, line in enumerate(textwrap.wrap(node['id'] + ' ' + node['title'], width=18)[:2]):
            parts.append(f'<text x="{x + 14}" y="{y + 25 + line_num * 19}" fill="{color}" class="node-title">{html.escape(line)}</text>')
        parts.append(f'<text x="{x + 14}" y="{y + 75}" fill="{color}">{LABELS[node["status"]]}</text></g>')
    parts.append('</svg>')
    return ''.join(parts)


HTML_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; font-src data:">
<title>@@TITLE@@</title><style>
@@REPORTSTYLE@@
@@THEME@@
@@PAGESTYLE@@
</style></head><body>@@PAGENAV@@<header class="site-header"><nav class="site-links" aria-label="阅读入口"><a href="reviewer-overview.html">审阅总览</a><a href="code-breakdown.html">代码拆解</a></nav><a class="site-brand" href="reviewer-overview.html">Simple Reviewer</a><div class="site-actions"><span class="site-status">完整审计记录</span><a class="site-button" href="report.md">文字版</a></div></header><main><div class="breadcrumbs">Simple Reviewer <span>/</span> <b>完整报告</b></div><header class="report-intro"><h1 id="title"></h1><p id="summary"></p><p id="meta" class="muted"></p><p id="journey" class="note"></p>
<p><a class="entry-link" href="reviewer-overview.html">返回审阅总览</a> <a href="code-breakdown.html">查看代码图解</a></p>
<div class="legend" aria-label="状态图例"><span class="badge passed">绿色 · 已验证通过</span><span class="badge failed">红色 · 已确认问题</span><span class="badge pending">黄色 · 待核实</span><span class="badge unchecked">灰色 · 未验证</span></div>
<p class="muted">点击节点查看职责、位置与证据。绿色只覆盖声明的验证范围。</p></header>
<p><a href="code-breakdown.html">打开 HTML 图文拆解</a> · <a href="code-breakdown.md">打开文字版</a></p>
<div class="columns"><section class="panel"><h2>代码职责流程图</h2><div class="graph">@@SVG@@</div>
<div class="toolbar"><button id="all" aria-pressed="true">全部节点</button><button id="problems" aria-pressed="false">仅问题与待验证</button></div><nav id="node-buttons" aria-label="节点选择"></nav><p id="filter-note" class="muted"></p></section>
<section class="panel" id="detail" aria-live="polite"><h2 id="node-title"></h2><div id="node-status"></div><dl id="node-details"></dl><div id="node-issues"></div><div id="node-evidence"></div></section></div>
<section class="panel"><h2>需求验收</h2><div class="table-wrap"><table><thead><tr><th>需求与来源</th><th>验收条件</th><th>状态</th><th>节点 / 证据</th></tr></thead><tbody id="requirements"></tbody></table></div></section>
<section class="panel"><h2>检查记录与快照</h2><div id="all-evidence"></div><details><summary>查看文件快照</summary><pre id="snapshot"></pre></details></section>
<footer>简单的审阅者1.0 · 离线报告，无网络请求。此文件是审查时的快照；代码或日志变化后需重新生成。工具校验引用及哈希，不替代需求判断、真实验证或端到端验收。</footer>
</main><script id="review-data" type="application/json">@@DATA@@</script><script>
'use strict';
const data=JSON.parse(document.getElementById('review-data').textContent);
const labels={passed:'已验证通过',failed:'已确认问题',pending:'待核实',unchecked:'未验证'};
const byId=items=>Object.fromEntries(items.map(item=>[item.id,item]));
const nodes=byId(data.nodes),evidence=byId(data.evidence),issues=byId(data.issues);
function el(tag,text,cls){const item=document.createElement(tag);if(text!==undefined)item.textContent=text;if(cls)item.className=cls;return item;}
function badge(status){return el('span',labels[status],'badge '+status);}
function facts(target,pairs){target.replaceChildren();for(const [key,value] of pairs){target.append(el('dt',key),el('dd',value||'未记录'));}}
function evidenceDetail(check){const details=el('details');details.append(el('summary',check.id+' · '+check.kind+' / '+check.outcome+(data.stale_evidence.includes(check.id)?' · 证据已过期':'')));const list=el('dl');facts(list,[['操作/命令',check.command],['工作目录',check.cwd],['退出码',String(check.exit_code??'不适用')],['预期',check.expected],['观察',check.observed],['验证范围',check.scope],['关联文件',check.source_files.join(', ')],['日志',check.log_path||'静态检查'],['日志哈希',check.log_sha256||'不适用']]);details.append(list);return details;}
document.getElementById('title').textContent=data.title;
document.getElementById('summary').append(el('strong','总体结论：'),badge(data.overall));
document.getElementById('meta').textContent=data.reviewed_at+' · '+data.mode+' · '+data.project_root;
document.getElementById('journey').textContent=data.journey_note||'完整路径范围以证据说明为准，未声明路径不视为通过。';
let selected=null,onlyProblems=false;
function selectNode(id){selected=id;const node=nodes[id];document.getElementById('node-title').textContent=node.id+' · '+node.title;document.getElementById('node-status').replaceChildren(badge(node.status));facts(document.getElementById('node-details'),[['应有作用',node.expected],['实际行为',node.actual],['输入',node.input],['输出',node.output],['代码位置',node.locations.map(p=>p.path+':'+p.line).join('\n')],['验证范围',node.scope],['状态依据',node.reason],['对应需求',node.requirement_ids.join(', ')],['受影响于',(node.affected_by||[]).join(', ')||'未登记']]);const issueArea=document.getElementById('node-issues');issueArea.replaceChildren();for(const key of node.issue_ids){const issue=issues[key];issueArea.append(el('h3',issue.id+' · '+issue.title+(issue.stale?'（待复验）':'')),el('p',(issue.status==='confirmed'?'已确认':'待核实')+' · '+(issue.severity==='blocking'?'阻断':'非阻断')),el('p','影响：'+issue.impact),el('p','建议：'+issue.suggestion));}const evidenceArea=document.getElementById('node-evidence');evidenceArea.replaceChildren(el('h3','关联证据'));if(!node.evidence_ids.length)evidenceArea.append(el('p','尚无实际验证证据。','muted'));for(const key of node.evidence_ids)evidenceArea.append(evidenceDetail(evidence[key]));document.querySelectorAll('[data-node]').forEach(item=>item.setAttribute('aria-pressed',String(item.dataset.node===id)));}
function drawButtons(){const nav=document.getElementById('node-buttons');nav.replaceChildren();const visible=data.nodes.filter(n=>!onlyProblems||n.status!=='passed');for(const node of visible){const button=el('button',node.id+' '+labels[node.status]);button.dataset.node=node.id;button.setAttribute('aria-pressed',String(node.id===selected));button.addEventListener('click',()=>selectNode(node.id));nav.append(button);}document.getElementById('filter-note').textContent=onlyProblems?'筛选只调整下方节点列表，完整流程图保留所有连接。'+(!visible.length?' 当前无问题或待验证节点。':''):'';if(visible.length&&!visible.some(n=>n.id===selected))selectNode(visible[0].id);}
document.querySelectorAll('.node').forEach(item=>{item.addEventListener('click',()=>selectNode(item.dataset.node));item.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();selectNode(item.dataset.node);}});});
for(const [id,flag] of [['all',false],['problems',true]])document.getElementById(id).addEventListener('click',()=>{onlyProblems=flag;document.getElementById('all').setAttribute('aria-pressed',String(!flag));document.getElementById('problems').setAttribute('aria-pressed',String(flag));drawButtons();});
for(const requirement of data.requirements){const row=el('tr');row.append(el('td',requirement.id+' '+requirement.text+'\n来源：'+requirement.source),el('td',requirement.acceptance));const status=el('td');status.append(badge(requirement.status));row.append(status,el('td',requirement.node_ids.join(', ')+' / '+requirement.evidence_ids.join(', ')));document.getElementById('requirements').append(row);}
for(const check of data.evidence)document.getElementById('all-evidence').append(evidenceDetail(check));
document.getElementById('snapshot').textContent=JSON.stringify(data.snapshot,null,2);
drawButtons();selectNode((data.nodes.find(n=>n.status==='failed')||data.nodes.find(n=>n.status==='pending')||data.nodes[0]).id);
</script></body></html>'''


def page_navigation(current, full_review=True, guide=None):
    pages = ([('reviewer-overview.html', '审阅总览'), ('code-breakdown.html', '代码拆解'),
              ('report.html', '完整报告')] if full_review else [('code-breakdown.html', '代码拆解')])
    if guide:
        pages.append(guide)
    links = []
    for href, label in pages:
        active = ' aria-current="page"' if href == current else ''
        links.append(f'<a href="{html.escape(href, quote=True)}"{active}>{html.escape(label)}</a>')
    return '<nav class="page-navigation" aria-label="页面导航">' + ''.join(links) + '</nav>'


def illustrated_breakdown(data, include_overview=False, guide=None):
    """Render escaped explanations and current source excerpts; execute nothing."""
    esc = lambda value: html.escape(str(value), quote=True)
    badge = lambda state: f'<span class="badge {state}">{LABELS[state]}</span>'
    paragraph = lambda label, text: f'<div><small>{esc(label)}</small><p>{esc(text)}</p></div>'
    nodes = {n['id']: n for n in data['nodes']}
    issues = {i['id']: i for i in data['issues']}
    evidence = {e['id']: e for e in data['evidence']}
    root = Path(data['project_root'])

    def excerpt(loc):
        path = project_path(root, loc['path'])
        first, last = loc['line'], loc.get('end_line', loc['line'])
        label = f'{loc["path"]}:{first}' + (f'–{last}' if last != first else '')
        symbol = ' · ' + loc['symbol'] if loc.get('symbol') else ''
        parts = [f'<details class="source"><summary>{esc(label + symbol)}</summary>',
                 f'<p class="source-path">{esc(path)} · L{first}–{last}</p>']
        if loc['path'] in data['stale_files']:
            parts.append('<p class="warning">源码已变化或缺失；此处为当前文件，旧结论待复验。</p>')
        try:
            raw = path.read_bytes()
            registered = next(f['sha256'] for f in data['snapshot']['files'] if f['path'] == loc['path'])
            if hashlib.sha256(raw).hexdigest() != registered.lower() and loc['path'] not in data['stale_files']:
                raise ValueError('Source changed during rendering; regenerate the report')
            lines = raw.decode('utf-8-sig').splitlines()
            if first > len(lines) or last > len(lines):
                parts.append('<p class="warning">位置超出当前文件，无法展示该范围，请重新核对行号。</p>')
            else:
                stop = min(last, first + 119)
                rows = ''.join(f'<span class="code-line"><b>{i}</b><span>{esc(lines[i-1]) or " "}</span></span>'
                               for i in range(first, stop + 1))
                parts.append(f'<pre><code>{rows}</code></pre>')
                if stop < last:
                    parts.append(f'<p>仅展示前 120 行；登记范围 L{first}–{last}，请按位置查看余下源码。</p>')
        except (OSError, UnicodeError):
            parts.append('<p class="warning">源码缺失或不是 UTF-8 文本，未嵌入片段。</p>')
        parts.append('</details>')
        return ''.join(parts)

    def proof(check):
        stale = ' · 证据已过期，待复验' if check['id'] in data['stale_evidence'] else ''
        kind = '实际执行 / 操作' if check['kind'] == 'runtime' else '静态阅读（不能证明运行通过）'
        return (f'<details class="evidence"><summary>{check["id"]} · {esc(kind)} · '
                f'{esc(check["outcome"] + stale)}</summary><div class="facts">'
                + ''.join(paragraph(label, check[field]) for label, field in (
                    ('预期', 'expected'), ('观察', 'observed'), ('验证范围', 'scope'),
                    ('命令 / 操作记录（仅展示）', 'command'), ('工作目录', 'cwd')))
                + paragraph('退出码', check.get('exit_code'))
                + paragraph('日志', check.get('log_path', '无运行日志'))
                + paragraph('日志 SHA-256', check.get('log_sha256', '不适用')) + '</div></details>')

    navigation, content, catalog = [], [], []
    for block in data['blocks']:
        key, state = block['id'], block['status']
        members = [nodes[n] for n in block['node_ids']]
        navigation.append(f'<a href="#{key}"><b>{key}</b> {esc(block["title"])}{badge(state)}</a>')
        locations = [loc for node in members for loc in node['locations']]
        position = locations[0] if locations else None
        source_label = f'{position["path"]}:{position["line"]}' if position else '尚未登记源码位置'
        catalog.append(f'<a class="catalog-card" href="#{key}" data-block="{key}">'
                       f'<div class="catalog-card-head"><span class="catalog-icon">{key}</span><div>'
                       f'<h3>{esc(block["title"])}</h3><small>{len(members)} 个职责节点</small></div></div>'
                       f'<p>{esc(block["purpose"])}</p>{badge(state)}<div class="catalog-card-foot">'
                       f'<span>{esc(source_label)}</span><b>查看拆解 ↗</b></div></a>')
        content.append(f'<section class="block {state}" id="{key}"><div class="block-heading">'
                       f'<span class="block-no">{key}</span><h2>{esc(block["title"])}</h2>{badge(state)}</div>'
                       f'<p class="purpose">{esc(block["purpose"])}</p>')
        explanation = block.get('explanation', {})
        if explanation.get('summary'):
            content.append(f'<p>{esc(explanation["summary"])}</p>')
        content.append('<div class="reading-flow" aria-label="板块输入、职责与输出示意">'
                       + paragraph('输入', '；'.join(dict.fromkeys(n['input'] for n in members)))
                       + '<span class="arrow" aria-hidden="true">→</span>'
                       + paragraph('承担职责', block['purpose'])
                       + '<span class="arrow" aria-hidden="true">→</span>'
                       + paragraph('输出', '；'.join(dict.fromkeys(n['output'] for n in members))) + '</div>')
        if explanation.get('steps'):
            content.append('<h3>这块怎样工作</h3><p class="muted">审查者提供的逻辑示意，不代表执行轨迹。</p><ol class="steps">'
                           + ''.join(f'<li><strong>{esc(s["title"])}</strong><p>{esc(s["detail"])}</p></li>'
                                     for s in explanation['steps']) + '</ol>')
        if explanation.get('example'):
            example = explanation['example']
            content.append('<aside class="example"><h3>用一个例子理解</h3>'
                           + paragraph('示意输入', example['input'])
                           + paragraph('应有结果', example['expected'])
                           + paragraph('示意边界（不作为运行证据）', example['note']) + '</aside>')
        boundary = [e for e in data['edges'] if (e['source'] in block['node_ids']) != (e['target'] in block['node_ids'])]
        if boundary:
            content.append('<h3>与其他板块的关系</h3><ul class="relations">' + ''.join(
                f'<li><a href="#{e["source"]}">{e["source"]} {esc(nodes[e["source"]]["title"])}</a>'
                f' → <a href="#{e["target"]}">{e["target"]} {esc(nodes[e["target"]]["title"])}</a>'
                f' · {esc(e["kind"])} · {esc(e["label"])}</li>' for e in boundary) + '</ul>')
        for node in members:
            content.append(f'<article class="node-card {node["status"]}" id="{node["id"]}">'
                           f'<h3>{node["id"]} · {esc(node["title"])} {badge(node["status"])}</h3>'
                           '<div class="facts">' + paragraph('应有作用', node['expected'])
                           + paragraph('实际实现', node['actual'])
                           + paragraph('节点输入', node['input']) + paragraph('节点输出', node['output'])
                           + paragraph('这块实际起效了吗？', node['reason'])
                           + paragraph('验证范围 / 限制', node['scope']) + '</div>')
            if node.get('affected_by'):
                content.append(paragraph('受上游影响（自身状态单独判断）', ', '.join(node['affected_by'])))
            for req in (r for r in data['requirements'] if r['id'] in node['requirement_ids']):
                content.append(paragraph(f'对应需求 {req["id"]} · {req["status"]}',
                                         req['text'] + '；验收：' + req['acceptance']))
            for issue in (issues[i] for i in node['issue_ids']):
                issue_state = 'pending' if issue['stale'] or issue['status'] == 'suspected' else 'failed'
                content.append(f'<aside class="issue {issue_state}"><h4>{issue["id"]} · {esc(issue["title"])}</h4>'
                               + badge(issue_state) + paragraph('影响', issue['impact'])
                               + paragraph('建议', issue['suggestion'])
                               + paragraph('严重程度 / 证据', issue['severity'] + ' / ' + ', '.join(issue['evidence_ids'])) + '</aside>')
            content.append('<h4>代码在哪里</h4>')
            content.extend(excerpt(loc) for loc in node['locations'])
            if not node['locations']:
                content.append('<p class="muted">未提供实现或源码位置，不能编造片段。</p>')
            content.append('<h4>生效证据</h4>')
            content.extend(proof(evidence[e]) for e in node['evidence_ids'])
            if not node['evidence_ids']:
                content.append('<p class="muted">尚无验证证据。</p>')
            content.append('</article>')
        content.append('</section>')
    template = (Path(__file__).resolve().parent.parent / 'assets' / 'code-breakdown.html').read_text(encoding='utf-8')
    values = {'TITLE': esc(data['title']), 'DATE': esc(data['reviewed_at']),
              'NAV': ''.join(navigation), 'CONTENT': ''.join(content), 'GRAPH': graph_svg(data),
              'JOURNEY': esc(data.get('journey_note', data['block_grouping'])),
              'STATUS': badge(data['overall']),
              'SNAPSHOT': esc(json.dumps(data['snapshot'], ensure_ascii=False, indent=2)),
              'ROOT': esc(data['project_root']),
              'STYLES': (Path(__file__).resolve().parent.parent / 'assets' / 'reviewer-breakdown.css').read_text(encoding='utf-8'),
              'THEME': report_theme(), 'PREVIEWS': document_previews(data), 'CATALOG': ''.join(catalog),
              'BLOCKS': str(len(data['blocks'])), 'NODES': str(len(data['nodes'])),
              'EVIDENCECOUNT': str(len(data['evidence'])),
              'CONTEXT': context_sections(data)[0],
              'PAGESTYLE': (Path(__file__).resolve().parent.parent / 'assets' / 'page-navigation.css').read_text(encoding='utf-8'),
              'PAGENAV': page_navigation('code-breakdown.html', include_overview, guide),
              'OVERVIEWLINK': '<p><a class="overview-link" href="reviewer-overview.html">打开审阅总览：先看懂，再决定</a></p>' if include_overview else ''}
    return re.sub(r'@@([A-Z]+)@@', lambda match: values[match.group(1)], template)


def render(record, record_dir, out_dir, breakdown_only=False, guide_page=None, guide_label='返回专题图解'):
    data = assess(record, record_dir)
    out = Path(out_dir).resolve()
    paths = {'breakdown': out / 'code-breakdown.md',
             'breakdown_html': out / 'code-breakdown.html'}
    if not breakdown_only:
        paths.update(markdown=out / 'report.md', html=out / 'report.html',
                     record=out / 'review.effective.json', overview=out / 'reviewer-overview.md',
                     overview_html=out / 'reviewer-overview.html')
    root = Path(data['project_root'])
    protected = {project_path(root, f['path']) for f in data['snapshot']['files']}
    protected.update(project_path(root, e['log_path']) for e in data['evidence'] if e['kind'] == 'runtime')
    need(not any(p.resolve() in protected for p in paths.values()), 'Output would overwrite reviewed source or evidence')
    guide = None
    if guide_page is not None:
        guide_path = Path(guide_page).resolve()
        need(guide_path.is_file() and guide_path.suffix.lower() == '.html', 'guide_page must be an existing HTML file')
        need(guide_path not in paths.values(), 'Output would overwrite guide_page')
        need(isinstance(guide_label, str) and bool(guide_label.strip()), 'guide_label must be nonempty text')
        guide = (quote(Path(os.path.relpath(guide_path, out)).as_posix(), safe='/'), guide_label)
    page_style = (Path(__file__).resolve().parent.parent / 'assets' / 'page-navigation.css').read_text(encoding='utf-8')
    payload = json.dumps(data, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    report_values = {'TITLE': html.escape(data['title']), 'SVG': graph_svg(data), 'DATA': payload,
                     'THEME': report_theme(),
                     'REPORTSTYLE': (Path(__file__).resolve().parent.parent / 'assets' / 'reviewer-report.css').read_text(encoding='utf-8'),
                     'PAGESTYLE': page_style, 'PAGENAV': page_navigation('report.html', True, guide)}
    document = re.sub(r'@@([A-Z]+)@@', lambda match: report_values[match.group(1)], HTML_TEMPLATE)
    breakdown_document = illustrated_breakdown(data, include_overview=not breakdown_only, guide=guide)
    out.mkdir(parents=True, exist_ok=True)
    paths['breakdown'].write_text(code_breakdown(data), encoding='utf-8')
    paths['breakdown_html'].write_text(breakdown_document, encoding='utf-8')
    if not breakdown_only:
        paths['markdown'].write_text(markdown(data), encoding='utf-8')
        paths['html'].write_text(document, encoding='utf-8')
        paths['record'].write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        context_html, context_md = context_sections(data)
        template = (Path(__file__).resolve().parent.parent / 'assets' / 'reviewer-overview.html').read_text(encoding='utf-8')
        values = {'TITLE': html.escape(data['title']), 'DATE': html.escape(data['reviewed_at']),
                  'ROOT': html.escape(data['project_root']), 'STATUS': LABELS[data['overall']],
                  'STATUSCLASS': data['overall'],
                  'BLOCKS': str(len(data['blocks'])), 'CONTEXT': context_html,
                  'THEME': report_theme(), 'PREVIEWS': document_previews(data),
                  'NODES': str(len(data['nodes'])), 'EVIDENCECOUNT': str(len(data['evidence'])),
                  'STYLES': (Path(__file__).resolve().parent.parent / 'assets' / 'reviewer-overview.css').read_text(encoding='utf-8'),
                  'PAGESTYLE': page_style, 'PAGENAV': page_navigation('reviewer-overview.html', True, guide),
                  'BASELINE': html.escape(data['snapshot']['base_revision'])}
        overview_html = re.sub(r'@@([A-Z]+)@@', lambda match: values[match.group(1)], template)
        paths['overview_html'].write_text(overview_html, encoding='utf-8')
        paths['overview'].write_text(f'# {data["title"]} · 审阅总览\n\n目标状态：{LABELS[data["overall"]]}\n\n'
                                    + context_md + '\n[查看代码拆解](code-breakdown.md)\n', encoding='utf-8')
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['validate', 'render', 'breakdown'])
    parser.add_argument('record', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--guide-page', type=Path, help='Existing companion HTML page to link back to')
    parser.add_argument('--guide-label', default='返回专题图解', help='Companion page navigation label')
    args = parser.parse_args()
    try:
        record = json.loads(args.record.read_text(encoding='utf-8-sig'))
        data = assess(record, args.record.parent)
        if args.action in ('render', 'breakdown'):
            need(args.out is not None, f'{args.action} requires --out')
            paths = render(record, args.record.parent, args.out, breakdown_only=args.action == 'breakdown',
                           guide_page=args.guide_page, guide_label=args.guide_label)
            print(json.dumps({k: str(v) for k, v in paths.items()}, ensure_ascii=False))
        print(f'Validated: overall={data["overall"]}; stale_evidence={len(data["stale_evidence"])}')
        return 0
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
