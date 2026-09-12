"""Durable copy/move steps; status observes tasks without submitting writes."""

import hashlib
import json
from pathlib import PurePosixPath
import time
from uuid import uuid4

from ..env_file import env_lock
from .synology_files import nas_path, within
from .synology_profiles import private_json, read_private_json
from .synology_transport import command_budget, SynologyError


class OperationMixin:
    def _destination(self, source: str, destination: str, overwrite: bool) -> tuple[str,dict]:
        dest=nas_path(destination,root=False)
        src=self.info(source)
        existing=self._maybe_info(dest)
        if destination.endswith('/') and (not existing or existing['type']!='dir'):
            raise SynologyError('A trailing-slash destination must be an existing NAS directory.', 'not_found')
        if existing and existing['type']=='dir':
            dest=str(PurePosixPath(dest)/PurePosixPath(source).name)
            existing=self._maybe_info(dest)
        if dest==source or (src['type']=='dir' and within(dest,source)):
            raise SynologyError('A copy/move destination cannot be the source or its descendant.', 'path_conflict')
        if existing:
            if existing['type']!=src['type']:
                raise SynologyError('Source and destination have conflicting types.', 'type_conflict')
            if existing['type']=='dir':
                raise SynologyError('Copy/move does not merge existing directory trees.', 'conflict')
            if not overwrite:
                raise SynologyError('Destination exists; explicit --overwrite is required.', 'conflict')
        parent=self._directory(str(PurePosixPath(dest).parent))
        boundary=self._remote_boundary(parent['path'])
        self._check_remote(parent,boundary)
        if existing:
            self._check_remote(existing,boundary)
        return dest,src

    def _operation_steps(self, source: str, dest: str, move: bool, overwrite: bool, identifier: str) -> tuple[list,str | None]:
        source_path,destination=PurePosixPath(source),PurePosixPath(dest)
        def copy_step(path,folder,remove,replace=None):
            return {'api':'SYNO.FileStation.CopyMove','method':'start','version':3,
                    'params':{'path':[path],'dest_folder_path':str(folder),'remove_src':remove,
                              'overwrite':replace,'accurate_progress':True},'async':True}
        if source_path.name==destination.name:
            return [copy_step(source,destination.parent,move,True if overwrite else None)],None
        if move and source_path.parent==destination.parent and not overwrite:
            return [{'api':'SYNO.FileStation.Rename','method':'rename','version':2,
                     'params':{'path':[source],'name':[destination.name]}}],None
        stage=str(destination.parent/f'.co-operation-{identifier}')
        # A staging folder avoids overwriting an unrelated source-named file in
        # the destination. Only our empty folder is removed during cleanup.
        return [
            {'api':'SYNO.FileStation.CreateFolder','method':'create','version':2,
             'params':{'folder_path':[str(destination.parent)],'name':[PurePosixPath(stage).name],'force_parent':False}},
            copy_step(source,stage,move),
            {'api':'SYNO.FileStation.Rename','method':'rename','version':2,
             'params':{'path':[str(PurePosixPath(stage)/source_path.name)],'name':[destination.name]}},
            copy_step(str(PurePosixPath(stage)/destination.name),destination.parent,True,True if overwrite else None),
            {'api':'SYNO.FileStation.Delete','method':'delete','version':2,
             'params':{'path':[stage],'recursive':False}},
        ],stage

    def _operation_result(self, identifier: str, record: dict) -> dict:
        return {key:record.get(key) for key in ('source','destination','status','stage_path','task_id','error')}

    def _save_operation(self, identifier: str, record: dict) -> dict:
        self.state.save('operation',record,identifier)
        return {**self._operation_result(identifier,record),'operation_id':identifier,
                'resume':record['request'] if record['status']=='continuation_required' else None}

    def _poll_operation(self, identifier: str, record: dict, wait: bool) -> dict:
        step=record['steps'][record['index']]
        while True:
            try:
                data=self._request(step['api'],'status',version=step['version'],taskid=record['task_id'])
                if data.get('errors'):
                    raise SynologyError('DSM reported errors in the background task.', 'operation_failed')
                if data.get('finished') is True:
                    record['index']+=1
                    record['task_id']=None
                    record['status']='complete' if record['index']==len(record['steps']) else 'continuation_required'
                    return self._save_operation(identifier,record)
                if data.get('finished') is not False:
                    raise SynologyError('DSM did not return an unambiguous task state.', 'invalid_response')
                if not wait or self._remaining()<=.5:
                    return self._save_operation(identifier,record)
                time.sleep(min(.3,self._remaining()))
            except SynologyError as error:
                if error.code in {'timeout','network_error','http_error'}:
                    record['status']='operation_pending'
                    record['error']={'code':error.code,'message':'Task status was not confirmed; inspect this operation ID again.'}
                else:
                    # A NAS restart can discard its task history. Absence is
                    # never evidence that a copy or move did not happen.
                    record['status']='task_unavailable' if error.code in {'not_found','provider_error'} else 'operation_failed'
                    record['error']={'code':error.code,'message':str(error)}
                return self._save_operation(identifier,record)

    def _advance_operation(self, identifier: str, record: dict) -> dict:
        while record['index']<len(record['steps']):
            if record['status']=='operation_pending':
                result=self._poll_operation(identifier,record,True)
                if record['status']!='continuation_required':
                    return result
            if record['status'] not in {'ready','continuation_required'}:
                return self._save_operation(identifier,record)
            step=record['steps'][record['index']]
            try:
                self._remaining()
            except SynologyError:
                record['status']='continuation_required'
                return self._save_operation(identifier,record)
            # Persist uncertainty before any write, including synchronous
            # mkdir/rename/cleanup. A crashed process cannot replay the step.
            record['status']='submission_unknown'
            record['task_id']=None
            self._save_operation(identifier,record)
            try:
                data=self._request(step['api'],step['method'],version=step['version'],**step['params'])
                if data.get('errors'):
                    raise SynologyError('DSM reported a failed operation step.', 'operation_failed')
                if step.get('async'):
                    task=data.get('taskid')
                    if not isinstance(task,str) or not task:
                        raise SynologyError('DSM did not return a task ID; inspect remote paths before retrying.', 'submission_unknown')
                    record['task_id']=task
                    record['status']='operation_pending'
                else:
                    record['index']+=1
                    record['status']='continuation_required'
                record['error']=None
                self._save_operation(identifier,record)
            except SynologyError as error:
                record['status']='submission_unknown' if error.code=='submission_unknown' else 'operation_failed'
                record['error']={'code':error.code,'message':str(error)}
                return self._save_operation(identifier,record)
        record['status']='complete'
        return self._save_operation(identifier,record)

    @command_budget
    def operation_status(self, identifier: str, *, wait: bool = False) -> dict:
        with env_lock(self.state.path(identifier,'operation'),timeout=min(15,self._remaining())):
            record=self.state.read('operation',identifier)
            if record['status']=='operation_pending':
                return self._poll_operation(identifier,record,wait)
            return self._save_operation(identifier,record)

    def _copy_move(self, source: str, destination: str, *, move: bool, recursive: bool,
                   overwrite: bool, dry_run: bool) -> dict:
        source=nas_path(source,root=False)
        if move and len(PurePosixPath(source).parts)<3:
            raise SynologyError('Move operates inside shared folders; it cannot move a DSM shared root.', 'invalid_path')
        nas_path(destination,root=False)
        request={'source':source,'destination':destination,'move':move,'recursive':recursive,'overwrite':overwrite}
        key=hashlib.sha256(json.dumps([self.state.identity,request],sort_keys=True).encode()).hexdigest()
        intent=self.state.directory/'intents'/f'{key}.json'
        if not dry_run and intent.exists():
            identifier=read_private_json(intent)['operation_id']
            with env_lock(self.state.path(identifier,'operation'),timeout=min(15,self._remaining())):
                record=self.state.read('operation',identifier)
                if record['status']!='complete':
                    return self._advance_operation(identifier,record)
        dest,item=self._destination(source,destination,overwrite)
        if item['type']=='dir' and not (move or recursive):
            raise SynologyError('Copying a directory requires --recursive.', 'recursive_required')
        self._remote_tree(source,move or recursive)
        identifier=uuid4().hex
        steps,stage=self._operation_steps(source,dest,move,overwrite,identifier)
        for step in steps:
            self._api(step['api'],step['version'])
        if dry_run:
            return {'dry_run':True,'source':source,'destination':dest,'staging_required':bool(stage),
                    'steps':[{'api':s['api'],'method':s['method']} for s in steps]}
        with env_lock(intent,timeout=min(15,self._remaining())):
            if intent.exists():
                previous=read_private_json(intent)['operation_id']
                record=self.state.read('operation',previous)
                if record['status']!='complete':
                    return self.operation_status(previous)
            record={'request':request,'source':source,'destination':dest,'steps':steps,'index':0,
                    'status':'ready','stage_path':stage,'task_id':None,'error':None}
            self._save_operation(identifier,record)
            private_json(intent,{'operation_id':identifier})
        with env_lock(self.state.path(identifier,'operation'),timeout=min(15,self._remaining())):
            return self._advance_operation(identifier,record)

    @command_budget
    def copy(self, source: str, destination: str, *, recursive: bool = False,
             overwrite: bool = False, dry_run: bool = False) -> dict:
        return self._copy_move(source,destination,move=False,recursive=recursive,overwrite=overwrite,dry_run=dry_run)

    @command_budget
    def move(self, source: str, destination: str, *, overwrite: bool = False, dry_run: bool = False) -> dict:
        return self._copy_move(source,destination,move=True,recursive=True,overwrite=overwrite,dry_run=dry_run)
