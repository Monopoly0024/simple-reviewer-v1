"""Rebuild the reproducible demonstration record, not a real-project review."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    run = subprocess.run([sys.executable, '-B', 'verify_export.py'], cwd=ROOT,
                         encoding='utf-8', capture_output=True)
    log = ROOT / 'verification.log'
    log.write_bytes((run.stdout + run.stderr).encode('utf-8'))
    observed = json.loads(run.stdout)
    need = lambda key: next(c for c in observed['checks'] if c['id'] == key)
    evidence = []
    for key, scope in [('E1', '内存导出入口：跨页数据完整性'), ('E2', '状态筛选及列表两页分页'),
                       ('E3', '已返回记录的字段投影'), ('E4', '输入数据及对象独立性')]:
        check = need(key)
        evidence.append({'id': key, 'kind': 'runtime', 'command': 'python -B verify_export.py',
            'cwd': '.', 'exit_code': run.returncode,
            'outcome': 'passed' if check['passed'] else 'failed',
            'expected': check['expected'], 'observed': check['observed'], 'scope': scope,
            'source_files': ['orders.py', 'verify_export.py'],
            'log_path': 'verification.log', 'log_sha256': sha(log)})
    # The combined process exits 1 because E1 fails; successful independent subchecks
    # get their own zero-exit execution log instead of borrowing that failing run.
    for check in evidence:
        if check['outcome'] == 'passed':
            sub = subprocess.run([sys.executable, '-B', 'verify_export.py', '--check', check['id']],
                                 cwd=ROOT, encoding='utf-8', capture_output=True)
            sublog = ROOT / (check['id'] + '.log')
            sublog.write_bytes((sub.stdout + sub.stderr).encode('utf-8'))
            check.update(command=f'python -B verify_export.py --check {check["id"]}',
                         exit_code=sub.returncode, log_path=sublog.name, log_sha256=sha(sublog))
    evidence.append({'id': 'E5', 'kind': 'static', 'command': 'Read orders.py:1-9', 'cwd': '.',
        'exit_code': None, 'outcome': 'blocked', 'expected': '异常反馈策略需结合调用方确认',
        'observed': '函数通过字典键读取数据；未提供上层异常反馈入口，尚未执行异常场景。',
        'scope': '仅静态阅读，不确认错误，不作为本次必需需求', 'source_files': ['orders.py']})
    requirements = [
        {'id': 'R1', 'text': '导出全部符合状态的订单', 'source': '演示需求：全部匹配订单',
         'acceptance': '35条匹配订单返回35条，ID完整', 'required': True, 'status': 'failed',
         'node_ids': ['N2'], 'evidence_ids': ['E1']},
        {'id': 'R2', 'text': '字段为 id,status,total', 'source': '演示需求：指定导出字段',
         'acceptance': '已返回记录的字段集合和值正确', 'required': True, 'status': 'passed',
         'node_ids': ['N3'], 'evidence_ids': ['E3']},
        {'id': 'R3', 'text': '不修改源数据', 'source': '演示需求：保留原始输入',
         'acceptance': '调用前后深度相等，输出字典独立', 'required': True, 'status': 'passed',
         'node_ids': ['N3'], 'evidence_ids': ['E4']},
        {'id': 'R4', 'text': '列表默认每页20条', 'source': '演示需求：保持列表行为',
         'acceptance': '第一页20条、第二页15条，状态筛选正确', 'required': True, 'status': 'passed',
         'node_ids': ['N1'], 'evidence_ids': ['E2']},
        {'id': 'R5', 'text': '下载交付链路', 'source': '附加范围说明，未提供实现，非本例必需目标',
         'acceptance': '实际生成并下载后读取文件', 'required': False, 'status': 'unchecked',
         'node_ids': ['N5'], 'evidence_ids': []},
    ]
    def node(key, title, expected, actual, status, reason, line, reqs, checks, issue_ids=()):
        return {'id': key, 'title': title, 'role': 'implemented', 'expected': expected, 'actual': actual,
                'input': '订单集合与状态条件', 'output': '订单列表或投影后的记录',
                'scope': '演示程序的内存执行；未覆盖真实页面和下载', 'status': status, 'reason': reason,
                'locations': [{'path': 'orders.py', 'line': line}], 'requirement_ids': list(reqs),
                'evidence_ids': list(checks), 'issue_ids': list(issue_ids)}
    nodes = [
        node('N1', '筛选与列表分页', '按状态筛选，列表维持20条分页', '筛选后根据起点切片',
             'passed', '列表两页与状态条件符合预期', 1, ['R4'], ['E2']),
        node('N2', '导出取数', '取得全部符合条件的订单', '调用列表查询，继承默认第一页20条',
             'failed', '35条匹配订单只返回20条，复现了数据遗漏', 7, ['R1'], ['E1'], ['I1']),
        node('N3', '字段投影与返回', '保留指定字段并保持输入不变', '为每条已选订单创建新字典',
             'passed', '已返回记录字段与值正确，输入保持不变；不保证上游数据完整', 9, ['R2', 'R3'], ['E3', 'E4']),
        node('N4', '异常反馈路径', '结合调用方确认异常策略', '提供的函数没有上层异常反馈代码',
             'pending', '只有静态阅读，未执行异常场景，不判定缺陷', 9, [], ['E5']),
        node('N5', '文件生成与下载', '实际交付文件后回读内容', '未提供相应实现',
             'unchecked', '超出演示源码范围，尚未验证', 9, ['R5'], []),
    ]
    nodes[-1].update(role='unprovided', locations=[])
    nodes[0]['locations'][0].update(symbol='list_orders', end_line=4)
    nodes[1]['locations'][0].update(symbol='export_orders', end_line=9)
    nodes[2]['locations'][0].update(symbol='export_orders: 字段投影', end_line=9)
    nodes[3]['locations'][0].update(symbol='export_orders: 返回边界', end_line=9)
    record = {'schema_version': '1.0', 'title': '简单的审阅者1.0 · 订单导出示例',
        'reviewed_at': datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds'),
        'project_root': './order-export', 'mode': 'review',
        'journey_note': '已从 export_orders 入口执行35条匹配数据；导出遗漏15条。字段转换单独通过。实际下载和异常反馈尚未验证。此报告为内置示例。',
        'snapshot': {'base_revision': 'standalone-example', 'notes': '示例源代码未修改，缺陷故意保留以验证审阅者。',
                     'files': [{'path': name, 'sha256': sha(ROOT / name)} for name in ('orders.py', 'verify_export.py')]},
        'requirements': requirements, 'nodes': nodes,
        'blocks': [{'id': 'B1', 'title': '订单查询与分页',
                    'purpose': '为列表提供按状态筛选及每页20条的查询结果', 'node_ids': ['N1'],
                    'explanation': {'summary': '先找出匹配状态的订单，再只取当前页。',
                        'steps': [{'title': '筛选状态', 'detail': '根据 status 保留匹配记录。'},
                                  {'title': '计算起点', 'detail': '第一页从 0 开始，第二页从 20 开始。'},
                                  {'title': '切出当前页', 'detail': '每页最多 20 条，末页可以更少。'}],
                        'example': {'input': '35 条 paid 订单，第一页，每页 20 条',
                            'expected': '第一页 20 条，第二页 15 条。',
                            'note': '这是分页结构示意；实际运行结果见 E2。'}}},
                   {'id': 'B2', 'title': '导出服务',
                    'purpose': '取得全部匹配订单、生成指定字段的返回值，并明确异常边界', 'node_ids': ['N2', 'N3', 'N4'],
                    'explanation': {'summary': '导出复用了列表查询的默认分页，只取得 20 条。字段转换本身通过，数据完整性失败。',
                        'steps': [{'title': '调用列表查询', 'detail': '没有传 page/page_size，采用默认值。'},
                                  {'title': '继承第一页', 'detail': '35 条匹配订单到这里仅剩 20 条。'},
                                  {'title': '转换字段并返回', 'detail': '为已取得的记录创建新字典；不会找回遗漏记录。'}],
                        'example': {'input': '35 条匹配订单，要求全部导出',
                            'expected': '应返回 35 条；当前运行只返回 20 条。',
                            'note': '数字来自独立检查 E1；这里只帮助理解分页如何造成遗漏。'}}},
                   {'id': 'B3', 'title': '文件交付',
                    'purpose': '生成文件并交给用户下载；本例未提供实现', 'node_ids': ['N5']}],
        'edges': [{'source': 'N2', 'target': 'N1', 'label': '调用列表查询', 'kind': 'normal'},
                  {'source': 'N1', 'target': 'N3', 'label': '仅返回20条', 'kind': 'normal', 'issue_ids': ['I1']},
                  {'source': 'N3', 'target': 'N5', 'label': '交付关系未核实', 'kind': 'inferred'},
                  {'source': 'N3', 'target': 'N4', 'label': '异常策略待核实', 'kind': 'exception'}],
        'issues': [{'id': 'I1', 'title': '导出继承列表分页导致遗漏', 'status': 'confirmed',
                    'severity': 'blocking', 'node_ids': ['N2'], 'evidence_ids': ['E1'],
                    'impact': '匹配订单超过20条时导出不完整',
                    'suggestion': '拆分筛选与分页，导出使用全部筛选结果，保留列表原分页行为'}],
        'evidence': evidence}
    record['user_goal'] = {
        'original_request': '演示需求：导出全部符合状态的订单，字段为 id、status、total。',
        'plain_language': '列表可以分多页看，但导出应该拿到全部匹配数据。',
        'assumptions': ['仅验证内存中的示例数据，不连接真实订单系统。'],
        'open_questions': ['实际文件下载和异常反馈尚未验证。']}
    record['change_summary'] = {
        'baseline': '独立缺陷演示，无 AI 变更前的 Git 基线；不声称本次修改了业务代码。',
        'files_added': [], 'files_modified': [], 'files_deleted': [],
        'user_visible_changes': [],
        'possible_impacts': ['export_orders 复用列表默认分页，35 条匹配订单只返回 20 条。']}
    record['risks'] = [{
        'title': '数据交付不完整', 'action': '把导出结果作为完整订单清单使用',
        'status': 'not-run', 'impact': '本次只执行内存样例检查；没有生成真实订单文件。当前导出逻辑会遗漏 15 条。',
        'next_step': '修复分页复用后重跑完整性检查，再验证真实文件下载。'}]
    record['next_actions'] = [
        {'action': '先修复导出分页', 'reason': '把完整筛选结果和列表分页分开，保留原列表行为。'},
        {'action': '复验 35 条数据', 'reason': '重跑 E1，确认返回 35 条且订单 ID 完整。'},
        {'action': '单独检查下载和异常', 'reason': '当前样例没有提供完整页面和文件交付链路。'}]
    record['comprehension'] = {'glossary': [
        {'term': '分页', 'meaning': '把一份列表分几次显示；导出全部时不能只拿第一页。'},
        {'term': '运行证据', 'meaning': '实际执行得到的结果，仅证明记录中的输入和场景。'},
        {'term': '端到端', 'meaning': '从用户发起操作一直检查到最终收到结果，中间环节都需要覆盖。'}]}
    output = ROOT.parent / 'review.example.json'
    output.write_bytes((json.dumps(record, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(f'Rebuilt {output}; intentionally failing completeness check exit={run.returncode}')


if __name__ == '__main__':
    main()
