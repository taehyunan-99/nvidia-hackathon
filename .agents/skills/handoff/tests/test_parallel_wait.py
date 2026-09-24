import copy
import json
import os
import time
import unittest
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch
from test_parallel_contract import state_fixture, memory_mutator, runtime, contract
import parallel_wait as wait


class WaitCheckpointTests(unittest.TestCase):
    def state(self):
        state = state_fixture()
        for tid, task in state['tasks'].items():
            task.update(attempt=1, instruction_revision=1, status='RUNNING',
                        worker_id='app-'+tid, worker_thread_id='app-'+tid, worker_host_id='local')
        return state

    def begin(self, state, **options):
        request = {'turns': {'a':'exec-a','b':'exec-b'}, 'deadline_ms':int(time.time()*1000)+60000,
                   'evidence':'actual execution turns confirmed with app read_thread', **options}
        with patch.object(runtime, 'mutate', memory_mutator(state)):
            runtime.wait_begin('HANDOFF.md',state['revision'],'main-1',1,request)
        return state['wait_batch']

    def test_wait_preserves_active_run_approval_and_workers(self):
        state=self.state(); before=copy.deepcopy(state)
        checkpoint=self.begin(state)
        self.assertEqual(state['phase'],'ACTIVE')
        self.assertEqual(state['approval'],before['approval'])
        self.assertEqual(state['tasks'],before['tasks'])
        self.assertEqual(checkpoint['review_on'],'batch')
        contract.validate_state(state)

    def test_manual_wait_does_not_pause_or_generate_an_automatic_wake(self):
        state=self.state(); self.begin(state,mode='user',evidence='user explicitly selected manual resume')
        self.assertEqual(state['phase'],'ACTIVE')
        with self.assertRaisesRegex(contract.ParallelError,'manual'):
            wait.script(state,'.','helper.py')

    def test_stale_controller_attempt_plan_or_batch_rejected(self):
        for change in ('epoch','attempt','plan','batch'):
            state=self.state(); checkpoint=copy.deepcopy(self.begin(state))
            if change=='epoch': checkpoint['binding']['epoch']=2
            if change=='attempt': checkpoint['targets'][0]['attempt']=2
            if change=='plan': checkpoint['binding']['plan_hash']='wrong'
            if change=='batch': checkpoint['id']='another-batch'
            with self.subTest(change=change),self.assertRaises(contract.ParallelError):
                wait.save('HANDOFF.md',state,checkpoint)

    def test_duplicate_save_is_a_noop_and_regression_cannot_erase_candidates(self):
        state=self.state(); checkpoint=copy.deepcopy(self.begin(state))
        checkpoint['completed']=['a'];checkpoint['cursors']={'a':'opaque-cursor'};checkpoint['calls']=1
        with patch.object(runtime,'mutate',memory_mutator(state)):
            runtime.wait_save('HANDOFF.md',8,'main-1',1,checkpoint)
            runtime.wait_save('HANDOFF.md',9,'main-1',1,checkpoint)
        self.assertEqual(state['revision'],9)
        self.assertEqual(state['tasks']['a']['status'],'RUNNING')
        checkpoint=copy.deepcopy(checkpoint)
        checkpoint['completed']=[]
        with self.assertRaisesRegex(contract.ParallelError,'regressed'):
            wait.save('HANDOFF.md',state,checkpoint)

    def test_ready_is_only_a_review_hint_and_survives_reload(self):
        state=self.state(); checkpoint=copy.deepcopy(self.begin(state))
        checkpoint.update(completed=['a','b'],status='ready',calls=2)
        with patch.object(runtime,'mutate',memory_mutator(state)):
            runtime.wait_save('HANDOFF.md',8,'main-1',1,checkpoint)
        restored=json.loads(json.dumps(state));contract.validate_state(restored)
        self.assertEqual(restored['wait_batch']['status'],'ready')
        self.assertTrue(all(t['result'] is None and t['status']=='RUNNING' for t in restored['tasks'].values()))

    def test_question_wakes_before_the_batch_but_delayed_old_attempt_does_not(self):
        state=self.state(); checkpoint=self.begin(state)
        message={'schema':contract.MESSAGE_SCHEMA,'type':'UPDATE','run_id':state['run_id'],
                 'task_id':'a','sender':'app-a','attempt':1,'instruction_revision':1,'controller_epoch':1,
                 'message_id':'a'*32,'payload':{'kind':'QUESTION'}}
        with patch.object(Path,'glob',return_value=[Path('a'*32+'.json')]),patch.object(wait,'json_read',return_value=message):
            self.assertEqual(wait.save('HANDOFF.md',state,checkpoint)['status'],'attention')
            message['instruction_revision']=0
            self.assertEqual(wait.save('HANDOFF.md',state,checkpoint)['status'],'waiting')

    def test_generated_collector_round_trips_unicode_and_waits_for_checkpoint_command(self):
        node=shutil.which('node')
        if not node: self.skipTest('Node runtime unavailable')
        state=self.state(); self.begin(state,evidence='사용자가 확인한 실행 턴')
        code=wait.script(state,'.','helper.py')
        harness=r'''
const assert=require('node:assert/strict');
const source=require('node:fs').readFileSync(0,'utf8');
let saved,answer,calls=0,commandWaits=0;
const tools={
 mcp__codex_app__wait_threads:async ({targets})=>{calls++;return {polls:targets.map(t=>({thread:{id:t.threadId,hostId:t.hostId},latestTurn:{id:t.threadId.replace('app-','exec-'),status:'completed'},cursor:'opaque'}))};},
 exec_command:async ({cmd})=>{saved=JSON.parse(Buffer.from(cmd.split(' --checkpoint-base64 ')[1],'base64').toString('utf8'));return {session_id:17,output:''};},
 write_stdin:async ({session_id})=>{assert.equal(session_id,17);commandWaits++;return {exit_code:0,output:JSON.stringify({revision:9,checkpoint:saved})};}
};
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
new AsyncFunction('tools','text',source)(tools,x=>answer=x).then(()=>{
 assert.equal(answer.status,'ready');assert.equal(calls,1);assert.equal(commandWaits,1);
 assert.equal(saved.evidence,'사용자가 확인한 실행 턴');
}).catch(e=>{console.error(e);process.exitCode=1;});
'''
        result=subprocess.run([node,'-e',harness],input=code.encode(),capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))

    def test_generated_save_preserves_project_when_tool_cwd_changes(self):
        state=self.state(); self.begin(state)
        previous=Path.cwd()
        with tempfile.TemporaryDirectory() as folder:
            project=Path(folder)/'isolated project'; project.mkdir()
            caller=Path(folder)/'original clone'; caller.mkdir()
            try:
                os.chdir(project)
                code=wait.script(state,'.','helper.py')
                os.chdir(caller)
                line=next(line for line in code.splitlines() if line.startswith('const command = '))
                command=json.loads(line.removeprefix('const command = ').removesuffix(';'))
                self.assertIn("--project-root '"+str(project.resolve()).replace("'","''")+"'",command)
                self.assertNotIn("--project-root '.'",command)
            finally:
                os.chdir(previous)

    def test_real_receipt_checkpoint_round_trip_and_revision_conflict(self):
        from test_parallel_receipt import planned_receipt
        raw,state=planned_receipt()
        state.update(phase='ACTIVE',controller_id='main-1',controller_epoch=1)
        state['approval']={'plan_hash':contract.plan_hash(state['plan']),'evidence':'approved fixture','internal_git':True}
        for tid,task in state['tasks'].items():
            task.update(attempt=1,instruction_revision=1,status='RUNNING',worker_id='app-'+tid,worker_thread_id='app-'+tid,worker_host_id='local')
        raw=contract.embed(raw,state).replace('Receipt: READY','Receipt: STALE')
        with tempfile.TemporaryDirectory() as folder:
            receipt=Path(folder)/'HANDOFF.md';receipt.write_text(raw,encoding='utf-8')
            request={'turns':{'a':'exec-a','b':'exec-b'},'deadline_ms':int(time.time()*1000)+60000,'evidence':'verified fixture turns'}
            started=runtime.wait_begin(receipt,7,'main-1',1,request)
            checkpoint=copy.deepcopy(started['result']);checkpoint.update(status='ready',completed=['a','b'],calls=2)
            runtime.wait_save(receipt,8,'main-1',1,checkpoint)
            restored=runtime.load(receipt)
            self.assertEqual(restored['phase'],'ACTIVE')
            self.assertEqual(restored['wait_batch'],checkpoint)
            self.assertEqual(restored['tasks'],state['tasks'])
            with self.assertRaisesRegex(contract.ParallelError,'stale revision'):
                runtime.wait_save(receipt,8,'main-1',1,checkpoint)


if __name__=='__main__': unittest.main()
