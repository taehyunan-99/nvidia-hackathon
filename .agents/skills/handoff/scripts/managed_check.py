"""Durable command supervision: POSIX process groups or Windows Job Objects.

Commands must not daemonize or detach on POSIX. Unknown termination fails closed.
Run records live in the repository Git directory, never the skill directory.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid
from parallel_contract import common_dir, require, PROCESS_TERMINAL


_supervisors = {}


def save(path, data):
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(data), encoding='utf-8')
    os.replace(temp,path)


class PosixCommand:
    def __init__(self, argv, cwd, out, err):
        self.directory=Path(out.name).parent
        save(self.directory/'launch.json',{'argv':argv,'cwd':str(cwd)})
        self.p=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--posix-launch',str(self.directory)],
                                stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True)
    def poll(self):
        result=self.directory/'target-exit.json'
        if result.exists():return json.loads(result.read_text())['code']
        if self.p.poll() is not None:raise RuntimeError('process-group owner exited unexpectedly')
        return None
    def stop(self):
        # The launcher stays alive after the target exits, retaining ownership of its PGID.
        if self.p.poll() is not None:raise RuntimeError('process-group ownership lost; termination is unknown')
        os.killpg(self.p.pid,signal.SIGKILL)
        self.p.wait(timeout=10)
        until=time.monotonic()+5
        while time.monotonic()<until:
            try:os.killpg(self.p.pid,0)
            except ProcessLookupError:return
            time.sleep(.05)
        raise RuntimeError('process group termination is unknown')


def posix_launch(directory):
    directory=Path(directory)
    request=json.loads((directory/'launch.json').read_text())
    try:code=subprocess.call(request['argv'],cwd=request['cwd'],stdin=subprocess.DEVNULL)
    except OSError as exc:
        print(str(exc),file=sys.stderr);code=127
    save(directory/'target-exit.json',{'code':code})
    while True:time.sleep(1)


class TerminationUnknown(RuntimeError):
    def __init__(self, message, command):
        super().__init__(message)
        self.command=command


class WindowsCommand:
    def __init__(self, argv, cwd, out, err):
        # Create suspended, attach to a kill-on-close job, then resume: no launch race.
        import ctypes as c
        from ctypes import wintypes as w
        import msvcrt
        self.c=c; self.w=w; self.k=c.WinDLL('kernel32',use_last_error=True)
        H=w.HANDLE; D=w.DWORD; P=c.c_void_p; S=c.c_size_t
        class SI(c.Structure):
            _fields_=[('cb',D),('reserved',w.LPWSTR),('desktop',w.LPWSTR),('title',w.LPWSTR),
                      ('x',D),('y',D),('xs',D),('ys',D),('xc',D),('yc',D),('fill',D),('flags',D),
                      ('show',w.WORD),('reserved2',w.WORD),('data',P),('stdin',H),('stdout',H),('stderr',H)]
        class PI(c.Structure): _fields_=[('process',H),('thread',H),('pid',D),('tid',D)]
        class BASIC(c.Structure):
            _fields_=[('processTime',c.c_longlong),('jobTime',c.c_longlong),('flags',D),
                      ('minWS',S),('maxWS',S),('activeLimit',D),('affinity',S),('priority',D),('scheduling',D)]
        class IO(c.Structure): _fields_=[(n,c.c_ulonglong) for n in ('ro','wo','oo','rt','wt','ot')]
        class EXT(c.Structure):
            _fields_=[('basic',BASIC),('io',IO),('processMemory',S),('jobMemory',S),('peakProcess',S),('peakJob',S)]
        class ACCOUNT(c.Structure):
            _fields_=[(n,c.c_longlong) for n in ('user','kernel','userPeriod','kernelPeriod')]+[(n,D) for n in ('faults','total','active','terminated')]
        self.ACCOUNT=ACCOUNT
        signatures={
            'CreateJobObjectW':([P,w.LPCWSTR],H),'SetInformationJobObject':([H,c.c_int,P,D],w.BOOL),
            'CreateProcessW':([w.LPCWSTR,w.LPWSTR,P,P,w.BOOL,D,P,w.LPCWSTR,P,P],w.BOOL),
            'AssignProcessToJobObject':([H,H],w.BOOL),'ResumeThread':([H],D),
            'GetExitCodeProcess':([H,c.POINTER(D)],w.BOOL),'WaitForSingleObject':([H,D],D),
            'TerminateJobObject':([H,w.UINT],w.BOOL),'TerminateProcess':([H,w.UINT],w.BOOL),
            'QueryInformationJobObject':([H,c.c_int,P,D,P],w.BOOL),'CloseHandle':([H],w.BOOL)}
        for name,(args,result) in signatures.items():
            fn=getattr(self.k,name);fn.argtypes=args;fn.restype=result
        self.job=self.k.CreateJobObjectW(None,None); self.process=None;self.assigned=False;self.closed=False
        if not self.job: raise c.WinError(c.get_last_error())
        limit=EXT();limit.basic.flags=0x2000
        if not self.k.SetInformationJobObject(self.job,9,c.byref(limit),c.sizeof(limit)):
            self.k.CloseHandle(self.job); raise c.WinError(c.get_last_error())
        try:
            with open(os.devnull,'rb') as inp:
                handles=[msvcrt.get_osfhandle(f.fileno()) for f in (inp,out,err)]
                for h in handles:os.set_handle_inheritable(h,True)
                si=SI();si.cb=c.sizeof(si);si.flags=0x100;si.stdin,si.stdout,si.stderr=handles
                pi=PI()
                try:
                    if not self.k.CreateProcessW(None,c.create_unicode_buffer(subprocess.list2cmdline(argv)),None,None,True,
                                                0x4|0x08000000,None,str(cwd),c.byref(si),c.byref(pi)):
                        raise c.WinError(c.get_last_error())
                finally:
                    for h in handles:os.set_handle_inheritable(h,False)
            self.process=pi.process
            try:
                if not self.k.AssignProcessToJobObject(self.job,self.process): raise c.WinError(c.get_last_error())
                self.assigned=True
                if self.k.ResumeThread(pi.thread)==0xffffffff: raise c.WinError(c.get_last_error())
            finally:self.k.CloseHandle(pi.thread)
        except Exception as exc:
            if self.process:
                try:self.stop()
                except Exception as cleanup:raise TerminationUnknown(str(cleanup),self) from exc
            elif not self.closed:
                self.k.CloseHandle(self.job);self.closed=True
            raise
    def poll(self):
        # Exit code 259 is legal; wait state disambiguates it from STILL_ACTIVE.
        result=self.k.WaitForSingleObject(self.process,0)
        if result==258:return None
        if result!=0:raise self.c.WinError(self.c.get_last_error())
        code=self.w.DWORD()
        if not self.k.GetExitCodeProcess(self.process,self.c.byref(code)):raise self.c.WinError(self.c.get_last_error())
        return code.value
    def stop(self):
        if self.closed:return
        if not self.assigned:
            if self.k.WaitForSingleObject(self.process,0)!=0:
                if not self.k.TerminateProcess(self.process,1):raise self.c.WinError(self.c.get_last_error())
                if self.k.WaitForSingleObject(self.process,10000)!=0:raise RuntimeError('unassigned process termination is unknown')
            self.k.CloseHandle(self.process);self.k.CloseHandle(self.job);self.closed=True
            return
        if not self.k.TerminateJobObject(self.job,1):raise self.c.WinError(self.c.get_last_error())
        until=time.monotonic()+10
        while time.monotonic()<until:
            info=self.ACCOUNT()
            if not self.k.QueryInformationJobObject(self.job,1,self.c.byref(info),self.c.sizeof(info),None):
                raise self.c.WinError(self.c.get_last_error())
            if info.active==0:
                self.k.CloseHandle(self.process);self.k.CloseHandle(self.job);self.closed=True;return
            time.sleep(.05)
        raise RuntimeError('job termination is unknown')


def supervise(directory):
    directory=Path(directory)
    request=json.loads((directory/'request.json').read_text())
    status={'runId':directory.name,'status':'Starting','state':{},
            'stdoutPath':str(directory/'stdout'),'stderrPath':str(directory/'stderr')}
    process=None; terminal='Failed';code=None
    try:
        with open(directory/'stdout','wb') as out,open(directory/'stderr','wb') as err:
            process=(WindowsCommand if os.name=='nt' else PosixCommand)(request['argv'],request['cwd'],out,err)
            status['status']='Running';save(directory/'status.json',status)
            deadline=time.monotonic()+request['timeout']
            while True:
                code=process.poll()
                if code is not None:terminal='Completed';break
                if (directory/'stop').exists():terminal='Stopped';break
                if time.monotonic()>=deadline:terminal='TimedOut';break
                time.sleep(.05)
    except Exception as exc:
        status['error']=str(exc)
        if isinstance(exc,TerminationUnknown):process=exc.command;terminal='Unknown'
    finally:
        if process is not None:
            try:process.stop()
            except Exception as exc:terminal='Unknown';status['error']=str(exc)
        status.update(status=terminal,state={'targetExitCode':code})
        save(directory/'status.json',status)


def manager_call(root,action,**args):
    runs=common_dir(root)/'handoff-processes'
    if action=='Start':
        run_id=uuid.uuid4().hex;directory=runs/run_id;directory.mkdir(parents=True)
        request={'argv':[args['FilePath'],*args['ArgumentList']], 'cwd':str(Path(args['WorkingDirectory']).resolve()),
                 'timeout':args['TimeoutSeconds']}
        save(directory/'request.json',request)
        save(directory/'status.json',{'runId':run_id,'status':'Starting','state':{},
             'stdoutPath':str(directory/'stdout'),'stderrPath':str(directory/'stderr')})
        with open(directory/'supervisor.log','wb') as log:
            _supervisors[run_id] = subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--supervise',str(directory)],
                             stdin=subprocess.DEVNULL,stdout=log,stderr=log,close_fds=True,
                             **({'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=='nt' else {'start_new_session':True}))
        return json.loads((directory/'status.json').read_text())
    run_id=args['RunId'];require(re.fullmatch('[0-9a-f]{32}',run_id) is not None,'invalid process RunId')
    directory=runs/run_id
    require(directory.is_dir(),'unknown process RunId')
    if action=='Stop':
        (directory/'stop').touch()
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            result=json.loads((directory/'status.json').read_text())
            if result['status'] in PROCESS_TERMINAL:
                if run_id in _supervisors:_supervisors.pop(run_id).wait(timeout=2)
                return result
            if result['status']=='Unknown':raise RuntimeError(result.get('error','unknown termination'))
            time.sleep(.05)
        raise RuntimeError('supervisor termination is unknown; preserve evidence and workspace')
    require(action=='Status','unsupported process action')
    result=json.loads((directory/'status.json').read_text())
    if result['status'] in PROCESS_TERMINAL and run_id in _supervisors:
        _supervisors.pop(run_id).wait(timeout=2)
    return result

if __name__=='__main__':
    require(len(sys.argv)==3 and sys.argv[1] in {'--supervise','--posix-launch'},'internal supervisor invocation required')
    (supervise if sys.argv[1]=='--supervise' else posix_launch)(sys.argv[2])
