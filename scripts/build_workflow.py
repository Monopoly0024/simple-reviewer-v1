"""Build the English/Chinese landscape and portrait workflow diagrams."""
import base64
from html import escape
from pathlib import Path


ASSETS = Path(__file__).resolve().parent.parent / 'assets'
COPY = {
    'en': {
        'title': 'Understand what your AI actually built.',
        'sub': 'Simple Reviewer 1.2 / A readable Vibe Coding review',
        'input': ['Your code.', 'Your goals.', 'Your questions.'],
        'input_note': ['Start with ordinary words.', 'No coding vocabulary needed.'],
        'steps': [
            ('Clarify the goal', ['Turn intent into observable checks.', 'Keep assumptions and questions visible.']),
            ('Explain the changes', ['What changed? What will users see?', 'Compare files against a named baseline.']),
            ('Map the code', ['Explain inputs, duties, and outputs.', 'Show files, symbols, and line numbers.']),
            ('Verify the behavior', ['Run independent, relevant checks.', 'Record actual results and limitations.']),
            ('Surface the risks', ['Data, keys, permissions, cost.', 'Say what ran and what is unknown.']),
            ('Choose the next step', ['One clear action at a time.', 'Recheck affected paths after a fix.'])],
        'outputs': [('Read the overview', ['reviewer-overview.html / .md', 'Goals, changes, checks, risks, next steps']),
                    ('Explore the code', ['code-breakdown.html / .md', 'Block map, source locations, evidence']),
                    ('Keep the record', ['report.html / .md + effective JSON', 'Full review and snapshot for rechecking'])],
        'note': 'Overview and full record: render. Detailed explanation only: breakdown.',
        'legend': ['Verified in scope', 'Confirmed issue', 'Pending', 'Unchecked'],
        'footer': 'Status markers describe evidence. Panel fills organize the workflow; this is not a test result.'},
    'zh': {
        'title': '看懂 AI 写了什么，再决定下一步。',
        'sub': 'Simple Reviewer 1.2 / 为 Vibe Coding 提供可读、可核对的审阅',
        'input': ['你的代码', '你的目标', '你的问题'],
        'input_note': ['用日常语言描述就可以。', '不需要先学会编程术语。'],
        'steps': [
            ('把目标说清楚', ['把意图转成能观察的验收条件。', '假设和待确认问题单独保留。']),
            ('讲清 AI 的改动', ['改了哪里？用户会看到什么变化？', '基于明确的基线比较文件。']),
            ('拆解代码职责', ['解释输入、作用、输出与上下游。', '标出文件、符号和真实行号。']),
            ('核对实际行为', ['按独立预期执行适用检查。', '记录真实结果、范围与限制。']),
            ('突出影响与风险', ['数据、密钥、权限、费用等影响。', '说明是否执行，以及哪些仍未知。']),
            ('给出下一步', ['一次给出一个清楚的最小动作。', '修复后重新检查受影响路径。'])],
        'outputs': [('先看审阅总览', ['reviewer-overview.html / .md', '目标、变更、验证、风险和下一步']),
                    ('再读代码图解', ['code-breakdown.html / .md', '职责地图、源码位置和生效证据']),
                    ('保留复核记录', ['report.html / .md + effective JSON', '完整审查与文件快照，供后续复验'])],
        'note': 'render 生成总览和完整记录；breakdown 只生成代码拆解两文件。',
        'legend': ['范围内验证通过', '已确认问题', '待核实', '未验证'],
        'footer': '状态标记表示验证结论；黑白绿底色组织阅读层级。使用流程图不是实际检查结果。'}
}


def text(x, y, value, cls='body', fill=None):
    color = f' style="fill:{fill}"' if fill else ''
    return f'<text x="{x}" y="{y}" class="{cls}"{color}>{escape(value)}</text>'


def rect(x, y, w, h, fill='#fff', stroke='#d4ddd1', radius=12):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}"/>'


def document(language, mobile):
    c = COPY[language]
    width, height = (390, 1790) if mobile else (1440, 1060)
    heading = 28 if mobile else 44
    font = base64.b64encode((ASSETS / 'fonts/AlbertSans-VariableFont_wght.woff2').read_bytes()).decode('ascii')
    face = '@font-face{font-family:"Albert Sans";font-weight:100 900;src:url(data:font/woff2;base64,' + font + ') format("woff2");}'
    pieces = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
              f'<title id="title">Simple Reviewer: {escape(c["title"])}</title>',
              '<desc id="desc">Goals, changes, code map, verification, risks and next actions. HTML, Markdown and effective review record.</desc>',
              '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0 0L8 4L0 8Z" fill="#172017"/></marker></defs>',
              f'<style>{face}text{{font-family:"Albert Sans","PingFang SC","Microsoft YaHei",sans-serif;fill:#172017}}.hero{{font-size:{heading}px;font-weight:550;letter-spacing:-1px}}.title{{font-size:23px;font-weight:560}}.body{{font-size:18px;fill:#172017}}.small{{font-size:16px;fill:#596355}}.white{{font-size:26px;font-weight:550;fill:#fff}}.num{{font-size:18px;font-weight:600;fill:#70f28b}}.flow{{fill:none;stroke:#172017;stroke-width:2;marker-end:url(#arrow)}}</style>',
              rect(0, 0, width, height, '#f8f8f8', '#f8f8f8', 12)]
    if mobile:
        pieces += [text(22, 42, 'Simple Reviewer', 'title'), text(22, 72, 'Vibe Coding / 1.2.0', 'small')]
        hero_lines = ['Understand your code.', 'Choose your next step.'] if language == 'en' else ['看懂 AI 写了什么，', '再决定下一步。']
        pieces += [text(22, 120, hero_lines[0], 'hero'), text(22, 157, hero_lines[1], 'hero'),
                   rect(18, 188, 354, 112, '#20241f', '#20241f')]
        pieces += [text(36, 224, 'Code + goals + questions' if language == 'en' else '代码 + 目标 + 问题', 'white'),
                   text(36, 255, 'Start with ordinary words.' if language == 'en' else '用日常语言描述即可。', 'small', '#d6e2ca'),
                   text(36, 282, 'No coding vocabulary needed.' if language == 'en' else '不需要先学会编程术语。', 'small', '#d6e2ca')]
        for index, (title, detail) in enumerate(c['steps']):
            y = 332 + index * 145
            stage_fill = '#70f28b' if index == 3 else '#e1f1e1' if index == 5 else '#fff'
            pieces += [f'<path d="M195 {y-27}V{y-8}" class="flow"/>', rect(18, y, 354, 118, stage_fill),
                       rect(34, y+15, 38, 31, '#20241f', '#20241f', 16), text(42, y+37, f'{index+1:02d}', 'num'),
                       text(83, y+38, title, 'title'), text(34, y+75, detail[0], 'small'), text(34, y+101, detail[1], 'small')]
        y = 1216
        for index, (title, detail) in enumerate(c['outputs']):
            current = y + index * 123
            pieces += [rect(18, current, 354, 106, '#fff'),
                       text(34, current+32, title, 'title'), text(34, current+62, detail[0], 'small'), text(34, current+88, detail[1], 'small')]
        for index, (color, label) in enumerate(zip(['#21804e','#bd3434','#b58019','#858b92'], c['legend'])):
            x, y = 30 + (index % 2)*180, 1624 + (index//2)*42
            pieces += [f'<circle cx="{x}" cy="{y}" r="6" fill="{color}"/>', text(x+14, y+6, label, 'small')]
        foot = ['Panel fills organize the workflow.', 'A workflow is not a test result.'] if language == 'en' else ['底色组织阅读，状态标记表示结论。', '流程图不代表实际验证已经完成。']
        pieces += [text(22, 1730, foot[0], 'small'), text(22, 1758, foot[1], 'small')]
    else:
        pieces += [text(48, 57, 'Simple Reviewer', 'title'), rect(1202, 25, 186, 44, '#20241f', '#20241f', 22),
                   text(1225, 54, 'Vibe Coding / 1.2', 'num'), text(48, 137, c['title'], 'hero'), text(48, 181, c['sub'], 'body'),
                   rect(48, 226, 264, 410, '#20241f', '#20241f', 26)]
        for index, line in enumerate(c['input']):
            pieces.append(text(74, 292+index*47, line, 'white'))
        for index, line in enumerate(c['input_note']):
            pieces.append(text(74, 525+index*30, line, 'small', '#d6e2ca'))
        positions = [(355,226),(709,226),(1063,226),(1063,462),(709,462),(355,462)]
        for index, ((title, detail), (x,y)) in enumerate(zip(c['steps'], positions)):
            stage_fill = '#70f28b' if index == 3 else '#e1f1e1' if index == 5 else '#fff'
            pieces += [rect(x,y,326,174,stage_fill),rect(x+20,y+18,45,34,'#172017','#172017',8),text(x+30,y+42,f'{index+1:02d}','num'),
                       text(x+20,y+87,title,'title'),text(x+20,y+123,detail[0],'small'),text(x+20,y+150,detail[1],'small')]
        pieces += ['<path d="M315 310H345" class="flow"/>','<path d="M683 310H699" class="flow"/>',
                   '<path d="M1037 310H1053" class="flow"/>','<path d="M1226 403V451" class="flow"/>',
                   '<path d="M1060 550H1045" class="flow"/>','<path d="M706 550H691" class="flow"/>',
                   '<path d="M518 639V688" class="flow"/>']
        for index, (title, detail) in enumerate(c['outputs']):
            x = 48 + index*454
            pieces += [rect(x,708,434,155,'#fff'),text(x+24,751,title,'title'),
                       text(x+24,790,detail[0],'body'),text(x+24,831,detail[1],'small')]
        pieces.append(text(48,904,c['note'],'body'))
        for index, (color,label) in enumerate(zip(['#21804e','#bd3434','#b58019','#858b92'],c['legend'])):
            x=58+index*282
            pieces += [f'<circle cx="{x}" cy="957" r="8" fill="{color}"/>',text(x+20,964,label,'body')]
        pieces.append(text(48,1018,c['footer'],'small'))
    pieces.append('</svg>')
    return '\n'.join(pieces) + '\n'


if __name__ == '__main__':
    for language in ('en', 'zh'):
        for mobile in (False, True):
            name = 'workflow-mobile' if mobile else 'workflow-overview'
            suffix = '-en' if language == 'en' else ''
            (ASSETS / f'{name}{suffix}.svg').write_text(document(language, mobile), encoding='utf-8')
    print('Built four responsive workflow SVGs.')
