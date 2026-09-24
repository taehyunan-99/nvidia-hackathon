"""Exercise actual registration and command termination in owned temp repositories."""
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from parallel_contract import git,git_text,ParallelError,PROCESS_TERMINAL
from worktree_guard import register
from managed_check import manager_call

class PortableRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='handoff-portable-')
        self.base=Path(self.tmp.name).resolve();self.parent=self.base/'parent';self.parent.mkdir()
        git(self.parent,'init','-b','feat/parent')
        git(self.parent,'config','user.email','fixture@example.invalid')
        git(self.parent,'config','user.name','Fixture')
        hooks=self.base/'hooks';hooks.mkdir();git(self.parent,'config','core.hooksPath',str(hooks))
        (self.parent/'file.txt').write_text('original')
        git(self.parent,'add','--','file.txt');git(self.parent,'commit','-m','chore: fixture')
        self.sha=git_text(self.parent,'rev-parse','HEAD')
        self.child=self.base/'child-항체';git(self.parent,'worktree','add','--detach',str(self.child),self.sha)
    def tearDown(self):self.tmp.cleanup()
    def register(self,**changes):
        args=dict(parent=self.parent,root=self.child,branch='feat/child',parent_branch='feat/parent',commit=self.sha,
                  run_id='fixture-run',thread_id='fixture-thread',host_id='fixture-host');args.update(changes)
        return register(**args)
    def test_register_is_idempotent_and_rejects_another_owner(self):
        self.assertEqual(self.register(),self.register())
        with self.assertRaises(ParallelError):self.register(thread_id='other-thread')
        self.assertEqual(git_text(self.child,'branch','--show-current'),'feat/child')
    def test_dirty_checkout_remains_detached(self):
        (self.child/'file.txt').write_text('user work')
        with self.assertRaises(ParallelError):self.register()
        self.assertEqual(git_text(self.child,'branch','--show-current'),'')
        self.assertEqual((self.child/'file.txt').read_text(),'user work')
    def test_parent_cannot_be_adopted(self):
        with self.assertRaises(ParallelError):self.register(root=self.parent)
    def wait(self,run):
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            status=manager_call(self.parent,'Status',RunId=run)
            if status['status'] in PROCESS_TERMINAL or status['status']=='Unknown':return status
            time.sleep(.05)
        self.fail('supervisor did not terminate')
    def start(self,code,timeout=3):
        return manager_call(self.parent,'Start',FilePath=sys.executable,ArgumentList=['-c',code],
                            WorkingDirectory=str(self.parent),TimeoutSeconds=timeout)['runId']
    def test_uncertain_constructor_cleanup_never_becomes_terminal_failure(self):
        import managed_check as m
        directory=self.base/'failed-launch';directory.mkdir()
        m.save(directory/'request.json',{'argv':['unused'],'cwd':str(self.parent),'timeout':1})
        class UnknownProcess:
            def stop(self):raise RuntimeError('cannot confirm child stopped')
        with patch.object(m,'PosixCommand',side_effect=m.TerminationUnknown('creation cleanup unknown',UnknownProcess())), \
             patch.object(m,'WindowsCommand',side_effect=m.TerminationUnknown('creation cleanup unknown',UnknownProcess())):
            m.supervise(directory)
        status=json.loads((directory/'status.json').read_text())
        self.assertEqual(status['status'],'Unknown')
        self.assertNotIn(status['status'],PROCESS_TERMINAL)

    def test_nonzero_exit_and_output_survive(self):
        run=self.start("print('evidence');raise SystemExit(7)")
        result=self.wait(run)
        self.assertEqual(result['status'],'Completed');self.assertEqual(result['state']['targetExitCode'],7)
        self.assertIn('evidence',Path(result['stdoutPath']).read_text())
    def test_timeout_stops_command(self):
        run=self.start('import time;time.sleep(30)',timeout=1)
        self.assertEqual(self.wait(run)['status'],'TimedOut')
    def test_stop_is_idempotent(self):
        run=self.start('import time;time.sleep(30)',timeout=30)
        result=manager_call(self.parent,'Stop',RunId=run)
        self.assertEqual(result['status'],'Stopped')
        self.assertEqual(manager_call(self.parent,'Stop',RunId=run)['status'],'Stopped')
    def test_child_process_cannot_write_after_timeout(self):
        marker=self.parent/'late.txt'
        child="import time;from pathlib import Path;time.sleep(4);Path('late.txt').write_text('late')"
        run=self.start(f'import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",{child!r}]);time.sleep(30)',timeout=1)
        self.assertEqual(self.wait(run)['status'],'TimedOut')
        time.sleep(4)
        self.assertFalse(marker.exists())

if __name__=='__main__':unittest.main()
