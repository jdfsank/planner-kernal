"""JSON CLI facade; domain mutations all flow through Engine.apply."""
from __future__ import annotations

import argparse
import json
import sys

from .checks import run_checks, verify_check_baseline
from .contracts import KernelError, canonical, read_json, require, runtime_path, validate_document, write_new
from .execution import Engine
from .kernel import validate_state
from .packets import export_module, export_task, impact_report, resume_context


def parser():
    root=argparse.ArgumentParser(description='Explicit-only project planning kernel (Python 3.12, POSIX).')
    sub=root.add_subparsers(dest='command',required=True)
    commands={}
    for name in ('init','resume','query','validate','apply','archive','render','export-task',
                 'export-module','impact','run-check'):
        p=sub.add_parser(name);p.add_argument('--project',required=True)
        commands[name]=p
    commands['init'].add_argument('--explicit',action='store_true',help='Attest current user explicitly enabled planner-kernal')
    commands['init'].add_argument('--no-git-exclude',action='store_true')
    for name in ('apply','archive'):
        commands[name].add_argument('--input',required=True)
        commands[name].add_argument('--expected-revision',type=int)
    commands['query'].add_argument('--id')
    commands['query'].add_argument('--type',choices=['goals','architectures','contracts','modules','connections',
                                                     'stages','tasks','outputs','decisions','blockers',
                                                     'acceptances','evidence','archives'])
    commands['query'].add_argument('--status')
    commands['query'].add_argument('--stage')
    commands['query'].add_argument('--subject')
    commands['query'].add_argument('--revision',type=int)
    commands['export-task'].add_argument('--task',required=True)
    commands['export-task'].add_argument('--output')
    commands['export-module'].add_argument('--module',required=True)
    commands['impact'].add_argument('--module')
    commands['impact'].add_argument('--contract')
    commands['run-check'].add_argument('--task',required=True)
    commands['run-check'].add_argument('--task-revision',type=int,required=True)
    commands['run-check'].add_argument('--session',required=True)
    commands['run-check'].add_argument('--result',required=True)
    return root


def query(engine,state,args):
    if args.type in ('evidence','archives'):
        index=state['evidence_index' if args.type=='evidence' else 'archive_index']
        if args.id:
            require(args.id in index,'Unknown record ID')
            return engine.store.read_record(index[args.id])
        return {key:value for key,value in index.items() if
                (not args.subject or value.get('subject_id')==args.subject) and
                (not args.status or value.get('status')==args.status) and
                (args.revision is None or value.get('subject_revision')==args.revision)}
    entities=state['entities']
    registry=entities[args.type] if args.type else {key:value for values in entities.values() for key,value in values.items()}
    if args.id:
        require(args.id in registry,'Unknown entity ID')
        return registry[args.id]
    return {key:value for key,value in registry.items() if
            (not args.status or value.get('status')==args.status) and
            (not args.stage or value.get('stage_id')==args.stage) and
            (args.revision is None or value['revision']==args.revision)}


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        require(sys.version_info >= (3,12),'Python 3.12 required')
        engine=Engine(args.project)
        exit_code=0
        if args.command=='init':
            require(args.explicit,'init requires --explicit after current user invocation','EXPLICIT_REQUIRED')
            result=engine.store.init(git_exclude=not args.no_git_exclude)
        elif args.command in ('apply','archive'):
            op=read_json(args.input)
            validate_document(op,'operation')
            if args.command=='archive': require(op['kind']=='archive_pending_plan','archive needs archive_pending_plan operation')
            if args.expected_revision is not None:
                require(op['expected_revision']==args.expected_revision,'CLI/body revision mismatch')
            result=engine.apply(op)
        else:
            state=engine.store.load_state();validate_state(state)
            if args.command in ('resume','render'):
                result=resume_context(engine,state)
                if args.command=='render':
                    result={'text':json.dumps(result,ensure_ascii=False,indent=2),'authoritative':False}
            elif args.command=='query':result=query(engine,state,args)
            elif args.command=='validate':
                restored=resume_context(engine,state)
                result={'structure':'PASS','revision':state['revision'],
                        'freshness_warnings':restored['freshness_warnings'],'unreferenced_files':engine.store.orphans(),
                        'note':'Structure checks do not establish functional acceptance.'}
            elif args.command=='export-task':
                result=export_task(engine,state,args.task)
                if args.output:
                    output=runtime_path(engine.store.project,args.output)
                    require(output.is_relative_to(engine.store.root/'packets'),'Packets must be written under tmp_plan/packets')
                    write_new(output,canonical(result))
            elif args.command=='export-module':
                result=export_module(state,args.module)
            elif args.command=='impact':
                result=impact_report(state,args.module,args.contract)
            elif args.command=='run-check':
                require(state['session'] is not None and state['session']['id']==args.session and state['status']=='executing',
                        'Active execution session required','SESSION')
                task=state['entities']['tasks'].get(args.task)
                require(task is not None and task['revision']==args.task_revision,'Task revision mismatch','STALE')
                verify_check_baseline(task,engine.store.project)
                result=run_checks(task,engine.store.project,args.result,engine.skill_root)
                current=engine.store.load_state()
                require(current['session']==state['session'] and current['entities']['tasks'].get(args.task)==task,
                        'Execution session or task changed during check; do not register this result','STALE')
                exit_code=result['exit_code']
        print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
        return exit_code
    except (KernelError,OSError) as exc:
        print(json.dumps({'error':{'code':getattr(exc,'code','IO'),'message':str(exc)}},ensure_ascii=False))
        return 3


if __name__=='__main__':
    raise SystemExit(main())
