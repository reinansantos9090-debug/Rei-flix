import json, subprocess, sys, tempfile, unittest
from pathlib import Path
SCRIPT=Path(__file__).resolve().parents[1]/"scripts"/"prompt15_certification.py"
class Prompt15CertificationRunnerTests(unittest.TestCase):
    def test_runner_compiles(self):
        r=subprocess.run([sys.executable,"-m","py_compile",str(SCRIPT)],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False)
        self.assertEqual(r.returncode,0,r.stdout)
    def test_runner_marks_device_unvalidated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/"tests").mkdir()
            (root/"tests"/"__init__.py").write_text("",encoding="utf-8")
            (root/"tests"/"test_sample.py").write_text("import unittest\n\nclass SampleTests(unittest.TestCase):\n    def test_sample(self):\n        self.assertTrue(True)\n",encoding="utf-8")
            report=root/"report.json"; markdown=root/"report.md"
            subprocess.run(["git","init","-q",str(root)],check=True)
            subprocess.run(["git","-C",str(root),"config","user.email","test@example.invalid"],check=True)
            subprocess.run(["git","-C",str(root),"config","user.name","Prompt15 Test"],check=True)
            subprocess.run(["git","-C",str(root),"add","."],check=True)
            subprocess.run(["git","-C",str(root),"commit","-qm","fixture"],check=True)
            r=subprocess.run([sys.executable,str(SCRIPT),"--root",str(root),"--output",str(report),"--report",str(markdown)],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False)
            self.assertEqual(r.returncode,0,r.stdout)
            data=json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(data["classification"],"CERTIFICATION PARTIAL")
            self.assertIn("NOT VALIDATED",{x["status"] for x in data["results"]})
if __name__=="__main__": unittest.main()
