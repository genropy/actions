#!/usr/bin/env python3
"""Static check of a GenroPy project against the changes between genropy master
(26.10.28) and develop that can break application code.

    python3 compliance.py <project_dir> [<project_dir> ...] [--json] [--min LEVEL] [--fail-on LEVEL]

It reads the checkout as it is: point it at the branch that runs in production.
A finding is a place to look at, not a verdict. Exit code: 2 with HIGH findings,
1 with MEDIUM ones, 0 otherwise. --fail-on HIGH ignores MEDIUM findings in the
exit code, --fail-on NONE always exits 0 (report only).

A finding that is intended (e.g. a deliberate override of login_createNewUser)
is declared with a marker, on the reported line or alone on the line above it:

    def login_createNewUser(self, **kwargs):  # compliance: ok LOGIN-NEWUSER <reason>

    # compliance: ok ENV-KEY <reason>
    sede_id = self.db.currentEnv['sede_id']

The marker drops only findings of the RULE it names, and only with a reason.
For a function the reported line is the def line: put the marker after it.
An ENV-KEY finding is marked when any of the reads of its key carries the marker.
In .js files `//` works as well as `#`. Marked findings are listed after the
others with their reason (under "marked" with --json) and never fail the exit code.
"""

import argparse
import ast
import json
import os
import re
import sys
import warnings
from collections import defaultdict

LEVELS = ['HIGH', 'MEDIUM', 'LOW', 'INFO']
SKIP_DIRS = {'.git', '.claude', 'node_modules', '__pycache__', 'site-packages', 'dojo_libs', 'tests', '.venv', 'venv'}
HOOK_FORM = 'rootenvForm'
HOOK_SERVER = ('onUserSelected', 'onAuthenticating')
CUSTOM_LOGIN = {'login_doLogin', 'login_checkAvatar', 'loginDialog', 'login_newWindow', 'login_confirmUser'}
NEW_USER = {'login_createNewUser', 'login_newUser_form'}
CLIENT_WRITERS = {'dataFormula', 'dataRpc', 'dataController'}
ENV_NAMES = {'currentEnv', 'currentenv'}
# what the page puts in the db env by itself, whatever the login does
FRAMEWORK_KEYS = {'storename', 'dbbranch', 'workdate', 'locale', 'default_language', 'current_language', 'maxdate',
                  'mindate', 'user', 'userTags', 'pagename', 'mainpackage', 'external_host', 'currentDomain',
                  'user_id', 'user_group_code', 'language', 'login_date'}
MARKER = re.compile(r"(?:#|//)\s*compliance:\s*ok\s+([A-Z][A-Z0-9-]*)\s+(\S.*?)\s*$")
SET_ROOTENV = re.compile(r"\b(SET|PUT)\s+(\.[A-Za-z_]|gnr\.rootenv)")
JS_RULES = [
    ('ROOTENV-CLIENT-WRITE', 'HIGH', re.compile(r"setData\(\s*['\"]gnr\.rootenv|\bSET\s+gnr\.rootenv"),
     'the client writes the rootenv: after #1830 it reaches the server only on a declared serverpath'),
    ('SETINSERVER-ROOTENV', 'HIGH', re.compile(r"setInServer\(\s*['\"]rootenv"),
     'setInServer on a rootenv path is refused unless the page declared that serverpath (#1830)'),
    ('TINYMCE', 'HIGH', re.compile(r"\.(tinymce|tinyMCE|ExtendedTinyMCE)\(|tag\s*=\s*['\"]tinymce", re.I),
     'the tinyMCE widget is gone (#1793): use joditEditor'),
]
PY_LINE_RULES = JS_RULES + [
    ('ROOTENV-SERVERPATH', 'LOW', re.compile(r"serverpath\s*=\s*f?['\"]rootenv\."),
     'fine in the main build of a page; inside content built through remote it needs genropy #1852'),
]


class Finding(dict):
    def __init__(self, level, rule, path, line, message):
        super().__init__(level=level, rule=rule, file=path, line=line, message=message)


def const(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def rootenv_key(path):
    """The rootenv key of '^.x' / '=.x' / '.x' / 'gnr.rootenv.x', or None."""
    if not isinstance(path, str):
        return None
    path = path.lstrip('^=')
    for prefix in ('.', 'gnr.rootenv.'):
        if path.startswith(prefix):
            key = path[len(prefix):]
            return key if key and not re.search(r"[.?#]", key) else None
    return None


class Project:
    def __init__(self, root):
        self.root = root
        self.findings = []
        self.env_reads = defaultdict(list)      # key -> [(path, line)]
        self.env_writes = set()
        self.hook_keys = defaultdict(set)       # 'always' / 'sometimes' -> keys
        self.form_condition_keys = set()
        self.form_value_keys = set()            # keys edited by a field of the login form: the browser sends them
        self.declared_env_keys = set()          # keys a page declares with dbenv=True
        self.partitioned = []
        self.marked = []
        self._lines = {}

    def add(self, level, rule, path, line, message, places=None):
        """Record a finding on path:line, or among the marked ones when a marker on one of `places`
        (default: path:line) declares it intended."""
        finding = Finding(level, rule, os.path.relpath(path, self.root), line, message)
        for place in places or [(path, line)]:
            reason = self.marker_reason(*place, rule)
            if reason:
                finding['reason'] = reason
                self.marked.append(finding)
                return
        self.findings.append(finding)

    def marker_reason(self, path, line, rule):
        """The reason of a `# compliance: ok <rule> <reason>` marker ending the line or alone above it, or None."""
        if path not in self._lines:
            try:
                with open(path, encoding='utf-8', errors='replace') as f:
                    self._lines[path] = f.read().splitlines()
            except OSError:
                self._lines[path] = []
        lines = self._lines[path]
        above = lines[line - 2].strip() if 1 < line <= len(lines) + 1 else ''
        candidates = [lines[line - 1] if 0 < line <= len(lines) else '']
        if above.startswith(('#', '//')):
            candidates.append(above)
        for text in candidates:
            for marked_rule, reason in MARKER.findall(text):
                if marked_rule == rule:
                    return reason
        return None

    def scan(self):
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for name in sorted(filenames):
                path = os.path.join(dirpath, name)
                if name.endswith('.py'):
                    self.scan_py(path)
                elif name.endswith('.js') and '.min.' not in name:
                    self.scan_lines(path, JS_RULES)
        self.env_findings()
        if self.partitioned:
            path, line = self.partitioned[0]
            self.add('INFO', 'PARTITION', path, line,
                     '%i partition declarations: the current value now only narrows what the server allowed '
                     '(#1832, #1849); try the partition selector' % len(self.partitioned))
        return self

    def scan_lines(self, path, rules, source=None):
        try:
            source = source if source is not None else open(path, encoding='utf-8', errors='replace').read()
        except OSError:
            return
        for n, line in enumerate(source.splitlines(), 1):
            if line.lstrip().startswith(('#', '//')):
                continue
            for rule, level, pattern, message in rules:
                if pattern.search(line):
                    self.add(level, rule, path, n, message)
            if re.search(r"partition_\w+\s*=|def partition(ion)?ing_pkeys", line):
                self.partitioned.append((path, n))

    def scan_py(self, path):
        try:
            source = open(path, encoding='utf-8', errors='replace').read()
        except OSError:
            return
        self.scan_lines(path, PY_LINE_RULES, source)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                tree = ast.parse(source)
        except SyntaxError:
            if 'currentEnv[' in source or HOOK_FORM in source:
                self.add('INFO', 'UNPARSED', path, 1, 'not valid Python 3: read by hand')
            return
        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript) and const(node.slice) is not None \
                    and getattr(node.value, 'attr', getattr(node.value, 'id', None)) in ENV_NAMES:
                if isinstance(node.ctx, ast.Store):
                    self.env_writes.add(const(node.slice))
                else:
                    self.env_reads[const(node.slice)].append((path, node.lineno))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.scan_function(path, node)
            elif isinstance(node, ast.Call):
                kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
                if 'dbenv' in kwargs or 'attr_dbenv' in kwargs:
                    for path_value in [const(kwargs.get('serverpath')), const(kwargs.get('value')),
                                       const(node.args[0]) if node.args else None]:
                        if path_value:
                            self.declared_env_keys.add(re.split(r"[.^=]", path_value)[-1])

    def scan_function(self, path, func):
        name = func.name
        if name in CUSTOM_LOGIN:
            self.add('HIGH', 'LOGIN-CUSTOM', path, func.lineno,
                     '%s is redefined: the server-built rootenv (#1828) and the login checks of the framework '
                     'do not apply to it; rpcs called before login must be sessionless=True or referenced '
                     'by a node of the login page' % name)
        elif name in NEW_USER:
            self.add('MEDIUM', 'LOGIN-NEWUSER', path, func.lineno,
                     '%s is redefined: login_createNewUser now honours the new_user preference and keeps only '
                     'the fields of login_newUserFields' % name)
        elif name.startswith('loginExtra'):
            self.add('INFO', 'LOGIN-EXTRA', path, func.lineno,
                     'loginExtra hooks run only when the dialog performs a login (#1732)')
        if name.startswith(HOOK_FORM):
            self.scan_form(path, func)
        elif name.startswith(HOOK_SERVER):
            self.scan_server_hook(func)
        if self.is_login_rpc(func):
            args = {a.arg for a in func.args.args}
            if args & {'user_id', 'username', 'user'} and not name.startswith('login_'):
                self.add('MEDIUM', 'PRELOGIN-RPC', path, func.lineno,
                         '%s is a public rpc of the login that takes the user from the client' % name)

    def is_login_rpc(self, func):
        for deco in func.decorator_list:
            text = ast.unparse(deco)
            if 'public_method' in text and 'sessionless=True' not in text and 'tags=False' in text:
                return True
        return False

    def scan_server_hook(self, func):
        def keys_of(stmt):
            for node in ast.walk(stmt):
                if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store) and const(node.slice) \
                        and getattr(node.value, 'id', None) in ('data', 'rootenv'):
                    yield const(node.slice)
                elif isinstance(node, ast.Call) and getattr(node.func, 'attr', None) == 'setItem' \
                        and getattr(node.func.value, 'id', None) in ('data', 'rootenv') and node.args:
                    if const(node.args[0]):
                        yield const(node.args[0])
        seen_return = False
        for stmt in func.body:
            straight = isinstance(stmt, (ast.Assign, ast.AugAssign, ast.Expr)) and not seen_return
            self.hook_keys['always' if straight else 'sometimes'].update(keys_of(stmt))
            if any(isinstance(n, ast.Return) for n in ast.walk(stmt)):
                seen_return = True

    def scan_form(self, path, func):
        for node in ast.walk(func):
            if not isinstance(node, ast.Call):
                continue
            widget = getattr(node.func, 'attr', '')
            kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
            first = const(node.args[0]) if node.args else None
            strings = [const(a) for a in node.args] + [const(v) for v in kwargs.values()]
            if widget in CLIENT_WRITERS and (rootenv_key(first) or any(s and SET_ROOTENV.search(s) for s in strings)):
                self.add('HIGH', 'LOGIN-CLIENT-WRITE', path, node.lineno,
                         '%s writes a rootenv key in the browser: the login keeps only the form fields (#1828); '
                         'compute it in onUserSelected or onAuthenticating' % widget)
            elif any(s and SET_ROOTENV.search(s) for s in strings):
                self.add('HIGH', 'LOGIN-CLIENT-WRITE', path, node.lineno,
                         'an attribute of %s writes a rootenv key in the browser: set it in onAuthenticating' % widget)
            if widget == 'data' and rootenv_key(first) and (len(node.args) < 2 or const(node.args[1]) is None
                                                             and isinstance(node.args[1], ast.Constant)):
                self.add('LOW', 'LOGIN-DATA-NONE', path, node.lineno,
                         "data('.%s') without a value no longer leaves the key in the rootenv" % rootenv_key(first))
            value = const(kwargs.get('value'))
            if value and value[:1] in ('^', '=') and rootenv_key(value):
                self.form_value_keys.add(rootenv_key(value))
            if value and value[:1] == '^' and value[1:2] == '.' and not rootenv_key(value):
                self.add('MEDIUM', 'LOGIN-FIELD-PATH', path, node.lineno,
                         "the field value %s is not a direct rootenv key: the login does not keep it" % value)
            for arg, val in kwargs.items():
                if arg.startswith('condition_') and rootenv_key(const(val) or ''):
                    self.form_condition_keys.add(rootenv_key(const(val)))
            selected = [a for a in kwargs if a.startswith('selected_')]
            if selected:
                dynamic = [a for a in ('dbtable', 'table', 'condition', 'columns')
                           if (const(kwargs.get(a)) or '')[:1] in ('^', '=')]
                if widget.lower() != 'dbselect' or {'selectmethod', '_storename', 'method'} & set(kwargs) or dynamic:
                    self.add('MEDIUM', 'LOGIN-SELECTED', path, node.lineno,
                             'selected_* on %s is not read again by the server (#1846): only a plain dbSelect '
                             'with a fixed table and condition is' % widget)
                for arg in selected:
                    target = const(kwargs[arg]) or ''
                    if not rootenv_key(target.partition('=')[0]):
                        self.add('INFO', 'LOGIN-SELECTED-TARGET', path, node.lineno,
                                 '%s=%r does not target a rootenv key: it stays on the client' % (arg, target))

    def env_findings(self):
        for key, places in sorted(self.env_reads.items()):
            if key in FRAMEWORK_KEYS or key in self.env_writes or key in self.hook_keys['always']:
                continue
            where = '%i read%s with [...]' % (len(places), '' if len(places) == 1 else 's')
            sometimes = key in self.hook_keys['sometimes']
            if key in self.form_condition_keys and key not in self.form_value_keys:
                level = 'HIGH'
                why = '%s and the login form only reads it in a condition: the browser no longer sends it ' \
                      'back (#1828)' % ('a login hook sets it only on some paths' if sometimes else 'no login hook sets it')
            elif key in self.form_value_keys:
                level, why = 'LOW', 'a field of the login form edits it: present only when the browser sends the field'
            elif sometimes:
                level, why = 'MEDIUM', 'a login hook sets it only on some paths'
            elif key in self.declared_env_keys or key.startswith(('current_', 'allowed_')):
                level, why = 'LOW', 'expected from a partition, a preference or a serverpath declared with dbenv'
            else:
                level, why = 'MEDIUM', 'no login hook sets it'
            path, line = min(places)
            self.add(level, 'ENV-KEY', path, line,
                     "currentEnv['%s']: %s; %s. KeyError when missing: set it always or use .get()" % (key, where, why),
                     places=sorted(places))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('projects', nargs='+')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--min', default='LOW', choices=LEVELS, help='lowest level to show (default LOW)')
    parser.add_argument('--fail-on', default='MEDIUM', choices=['HIGH', 'MEDIUM', 'NONE'], type=str.upper,
                        help='lowest level that makes the exit code non-zero (default MEDIUM)')
    args = parser.parse_args()
    shown = LEVELS[:LEVELS.index(args.min) + 1]

    def order(f):
        return LEVELS.index(f['level']), f['rule'], f['file'], f['line']

    report, worst = {}, 0
    for root in args.projects:
        project = Project(os.path.abspath(root)).scan()
        report[root] = dict(findings=sorted((f for f in project.findings if f['level'] in shown), key=order),
                            marked=sorted(project.marked, key=order))
        levels = {f['level'] for f in project.findings}
        worst = max(worst, 2 if 'HIGH' in levels else 1 if 'MEDIUM' in levels else 0)
    if args.fail_on == 'NONE' or (args.fail_on == 'HIGH' and worst < 2):
        worst = 0
    if args.json:
        sys.stdout.write(json.dumps(report, indent=1) + '\n')
        return worst
    for root, result in report.items():
        findings, marked = result['findings'], result['marked']
        counts = ', '.join('%i %s' % (sum(f['level'] == lv for f in findings), lv) for lv in shown)
        if marked:
            counts += ', %i marked ok' % len(marked)
        sys.stdout.write('\n== %s: %s\n' % (root, counts))
        for f in findings:
            sys.stdout.write('%-6s %-22s %s:%i\n       %s\n' % (f['level'], f['rule'], f['file'], f['line'], f['message']))
        if marked:
            sys.stdout.write('-- marked ok\n')
        for f in marked:
            sys.stdout.write('%-6s %-22s %s:%i\n       ok: %s\n' % (f['level'], f['rule'], f['file'], f['line'], f['reason']))
    return worst


if __name__ == '__main__':
    sys.exit(main())
