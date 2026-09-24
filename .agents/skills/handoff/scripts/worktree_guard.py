"""Register only an explicitly selected, clean, pinned task worktree."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from parallel_contract import require, repository, common_dir, git, git_text, safe_path


def register(parent, root, branch, parent_branch, commit, run_id, thread_id, host_id):
    parent, root = Path(parent).resolve(), Path(root).resolve()
    require(repository(parent) == parent and repository(root) == root, 'exact Git roots required')
    require(root != parent and common_dir(root) == common_dir(parent), 'isolated worktree in same repository required')
    safe_path(root, str(root), absolute=True)
    records = git(parent, "worktree", "list", "--porcelain", "-z").stdout.split(b"\0")
    paths = [Path(os.fsdecode(r[9:])).resolve() for r in records if r.startswith(b"worktree ")]
    require(root in paths and root != paths[0], 'registered linked worktree required; never adopt primary')
    require(git_text(parent, 'branch', '--show-current') == parent_branch, 'parent branch changed')
    require(git(parent, 'merge-base', '--is-ancestor', commit, 'HEAD', check=False).returncode == 0, 'parent baseline lost')
    require(git_text(root, 'rev-parse', 'HEAD') == commit, 'child baseline changed')
    require(not git_text(root, 'status', '--porcelain', '--untracked-files=all', '--ignored'), 'child is not clean')
    require(branch not in {'main', 'master', parent_branch}, 'task branch must be distinct')
    git(root, 'check-ref-format', '--branch', branch)
    record = {'path': str(root), 'parent': str(parent), 'parentBranch': parent_branch,
              'baseSha': commit, 'runId': run_id, 'threadId': thread_id, 'hostId': host_id}
    key = f'branch.{branch}.handoff-registration'
    previous = git(parent, 'config', '--local', '--get', key, check=False)
    if previous.returncode == 0:
        require(json.loads(previous.stdout) == record, 'branch owned by another handoff registration')
    else:
        require(previous.returncode == 1, 'cannot inspect registration')
    current = git_text(root, 'branch', '--show-current')
    exists = git(root, 'show-ref', '--verify', '--quiet', 'refs/heads/' + branch, check=False).returncode == 0
    if exists:
        require(current == branch and previous.returncode == 0, 'existing branch is not this registered task')
    else:
        require(not current, 'never replace an existing checkout branch')
        require(git(root, 'show-ref', '--verify', '--quiet', 'refs/remotes/origin/' + branch, check=False).returncode != 0,
                'remote-tracking task branch already exists')
        # Persist ownership before checkout so interruption is reconcilable.
        git(parent, 'config', '--local', key, json.dumps(record, sort_keys=True))
        git(root, 'switch', '-c', branch, commit)
    require(git_text(root, 'rev-parse', 'HEAD') == commit and git_text(root, 'branch', '--show-current') == branch,
            'registration postcondition failed')
    return {'action': 'Registered', 'baseSha': commit, 'worktreePath': str(root), **record}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ('Branch','ParentBranch','ParentCommit','ParentWorktree','RunId','RegisterAppWorktree','AppThreadId','AppHostId'):
        p.add_argument('-' + flag, required=True)
    a=p.parse_args()
    print(json.dumps(register(a.ParentWorktree, a.RegisterAppWorktree, a.Branch, a.ParentBranch,
                              a.ParentCommit, a.RunId, a.AppThreadId, a.AppHostId)))

if __name__ == '__main__':
    main()
