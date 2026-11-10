"""Contract tests of compliance.py: a small project on disk in, findings out.

    python3 -m unittest discover compliance/tests
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'compliance.py')
SPEC = importlib.util.spec_from_file_location('compliance', SCRIPT)
compliance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compliance)


def write_project(root, files):
    for name, source in files.items():
        with open(os.path.join(root, name), 'w', encoding='utf-8') as f:
            f.write(textwrap.dedent(source))


class ProjectCase(unittest.TestCase):
    def scan(self, **files):
        """Scan a project made of `files` (name -> source); return the Project."""
        with tempfile.TemporaryDirectory() as root:
            write_project(root, files)
            return compliance.Project(root).scan()

    def rules(self, project, level=None):
        return [f['rule'] for f in project.findings if level is None or f['level'] == level]


LOGIN_FORM = """
    class Login(object):
        def rootenvForm_el_org(self, fb):
            fb.dbSelect(value='^.sede_id', dbtable='el_org.sede')
            fb.dbSelect(value='^.convegno_id', dbtable='el_org.convegno',
                        condition='$sede_id=:env_current_sede_id', condition_env_current_sede_id='=.sede_id')
"""
ENV_READ = """
    def sede(db):
        return db.currentEnv['sede_id']
"""


class TestConditionKeys(ProjectCase):
    def test_condition_key_that_is_also_a_field_is_low(self):
        project = self.scan(**{'login.py': LOGIN_FORM, 'model.py': ENV_READ})
        self.assertEqual([f['level'] for f in project.findings if f['rule'] == 'ENV-KEY'], ['LOW'])

    def test_condition_key_with_no_field_is_high(self):
        form = """
            class Login(object):
                def rootenvForm_el_org(self, fb):
                    fb.dbSelect(value='^.convegno_id', dbtable='el_org.convegno',
                                condition='$sede_id=:env_current_sede_id', condition_env_current_sede_id='=.sede_id')
        """
        project = self.scan(**{'login.py': form, 'model.py': ENV_READ})
        self.assertIn('ENV-KEY', self.rules(project, 'HIGH'))


class TestMarker(ProjectCase):
    def test_trailing_marker_drops_the_finding(self):
        source = """
            class Login(object):
                def login_createNewUser(self, **kwargs):  # compliance: ok LOGIN-NEWUSER takes only email and password
                    pass
        """
        project = self.scan(**{'login.py': source})
        self.assertEqual(project.findings, [])
        self.assertEqual([(f['rule'], f['reason']) for f in project.marked],
                         [('LOGIN-NEWUSER', 'takes only email and password')])

    def test_marker_on_the_line_above_drops_the_finding(self):
        source = """
            class Login(object):
                # compliance: ok LOGIN-NEWUSER registration does not depend on the new_user preference
                def login_newUser_form(self, **kwargs):
                    pass
        """
        self.assertEqual(self.scan(**{'login.py': source}).findings, [])

    def test_marker_of_another_rule_does_not_suppress(self):
        source = """
            class Login(object):
                def login_createNewUser(self, **kwargs):  # compliance: ok LOGIN-CUSTOM wrong rule
                    pass
        """
        self.assertEqual(self.rules(self.scan(**{'login.py': source})), ['LOGIN-NEWUSER'])

    def test_marker_without_reason_does_not_suppress(self):
        source = """
            class Login(object):
                def login_createNewUser(self, **kwargs):  # compliance: ok LOGIN-NEWUSER
                    pass
        """
        self.assertEqual(self.rules(self.scan(**{'login.py': source})), ['LOGIN-NEWUSER'])

    def test_marker_on_an_env_key_read(self):
        source = """
            def sede(db):
                # compliance: ok ENV-KEY set by onAuthenticating of the instance
                return db.currentEnv['sede_id']
        """
        self.assertEqual(self.scan(**{'model.py': source}).findings, [])

    def test_marker_on_any_read_of_an_env_key(self):
        first = """
            def sede(db):
                return db.currentEnv['sede_id']
        """
        second = """
            def sede(db):
                return db.currentEnv['sede_id']  # compliance: ok ENV-KEY set by onAuthenticating of the instance
        """
        project = self.scan(**{'a.py': first, 'b.py': second})
        self.assertEqual(project.findings, [])
        self.assertEqual([(f['file'], f['line']) for f in project.marked], [('a.py', 3)])

    def test_js_marker(self):
        source = "editor.tinymce({}); // compliance: ok TINYMCE page not served by the new genropy\n"
        self.assertEqual(self.scan(**{'page.js': source}).findings, [])


class TestReport(unittest.TestCase):
    def test_json_lists_marked_findings_and_they_do_not_fail(self):
        source = """
            class Login(object):
                def login_createNewUser(self, **kwargs):  # compliance: ok LOGIN-NEWUSER takes only email and password
                    pass
        """
        with tempfile.TemporaryDirectory() as root:
            write_project(root, {'login.py': source})
            run = subprocess.run([sys.executable, SCRIPT, root, '--json'], capture_output=True, text=True)
        report = json.loads(run.stdout)[root]
        self.assertEqual(run.returncode, 0)
        self.assertEqual(report['findings'], [])
        self.assertEqual([(f['rule'], f['reason']) for f in report['marked']],
                         [('LOGIN-NEWUSER', 'takes only email and password')])


if __name__ == '__main__':
    unittest.main()
