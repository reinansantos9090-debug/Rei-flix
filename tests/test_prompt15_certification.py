import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts"/"prompt15_certification.py"
sys.path.insert(0,str(ROOT/"scripts"))
import prompt15_certification as runner

class Prompt15CertificationRunnerTests(unittest.TestCase):
    def test_matrix_has_exactly_201_unique_real_requirements(self):
        self.assertEqual(len(runner.REQUIREMENTS),201)
        ids=[x[0] for x in runner.REQUIREMENTS]
        reqs=[x[2] for x in runner.REQUIREMENTS]
        areas=[x[1] for x in runner.REQUIREMENTS]
        self.assertEqual(ids,list(range(1,202)))
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(len(reqs),len(set(reqs)))
        self.assertTrue(all(reqs))
        self.assertTrue(all(areas))
        self.assertTrue(all(not x.startswith("Prompt 15.1 item") for x in reqs))

    def test_classifications_are_exactly_the_allowed_set(self):
        self.assertEqual(runner.ALLOWED,{"PASS","PARTIAL","FAIL","NOT VALIDATED","NOT APPLICABLE","BLOCKED BY ENVIRONMENT"})

    def test_empty_adb_list_is_not_device_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            bindir=Path(tmp)/"bin"; bindir.mkdir()
            adb=bindir/"adb"
            adb.write_text("#!/bin/sh\necho 'List of devices attached'\nexit 0\n",encoding="utf-8")
            adb.chmod(0o755)
            old=os.environ.get("PATH",""); os.environ["PATH"]=str(bindir)+os.pathsep+old
            try:
                probe=runner.adb_probe(Path(tmp))
            finally:
                os.environ["PATH"]=old
            self.assertEqual(probe["tool"],"PASS")
            self.assertEqual(probe["devices"],[])
            self.assertEqual(probe["device_validation"],"NOT VALIDATED")

    def test_failed_command_is_never_pass(self):
        result=runner.run_command("test","intentional failure",[sys.executable,"-c","raise SystemExit(7)"],cwd=ROOT,timeout=30)
        self.assertEqual(result.status,"FAIL")
        self.assertEqual(result.exit_code,7)

    def test_missing_paths_are_not_promoted_to_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            results={
                "pytest":runner.Result("Python","pytest","NOT VALIDATED","not run"),
                "unittest":runner.Result("Python","unittest","NOT VALIDATED","not run"),
            }
            row=runner.make_row(root,runner.REQUIREMENTS[0],results,{"status":"NOT VALIDATED"},[])
            self.assertNotEqual(row["Result"],"PASS")

    def test_source_never_executes_emulator_or_connected_instrumentation(self):
        source=SCRIPT.read_text(encoding="utf-8")
        self.assertNotRegex(source,r"(emulator\s+-avd|connectedDebugAndroidTest|connectedAndroidTest)\b")

    def test_runner_compiles(self):
        result=subprocess.run([sys.executable,"-m","py_compile",str(SCRIPT)],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False)
        self.assertEqual(result.returncode,0,result.stdout)

    def test_small_fixture_generates_201_rows_without_fake_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"tests").mkdir()
            (root/"tests"/"test_sample.py").write_text("def test_sample():\n    assert True\n",encoding="utf-8")
            subprocess.run(["git","init","-q",str(root)],check=True)
            subprocess.run(["git","-C",str(root),"config","user.email","test@example.invalid"],check=True)
            subprocess.run(["git","-C",str(root),"config","user.name","Prompt15 Test"],check=True)
            subprocess.run(["git","-C",str(root),"add","."],check=True)
            subprocess.run(["git","-C",str(root),"commit","-qm","fixture"],check=True)
            out=root/"out.json"; report=root/"report.md"; matrix=root/"matrix.json"
            result=subprocess.run([sys.executable,str(SCRIPT),"--root",str(root),"--skip-gradle","--output",str(out),"--report",str(report),"--matrix",str(matrix)],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False,timeout=180)
            self.assertEqual(result.returncode,0,result.stdout)
            data=json.loads(out.read_text(encoding="utf-8"))
            rows=json.loads(matrix.read_text(encoding="utf-8"))
            self.assertEqual(len(rows),201)
            self.assertEqual(len({x["ID"] for x in rows}),201)
            self.assertTrue(all(not x["Requirement"].startswith("Prompt 15.1 item") for x in rows))
            self.assertEqual(sum(data["matrix_counts"].values()),201)

if __name__=="__main__":
    unittest.main()
