"""Host wiring for review, authored updates and authenticated UI controls."""
import asyncio
import difflib
import hashlib
import logging
import time
from pathlib import Path

from .bundle import capture_bundle, media_type, validate_path
from .runtime import ControlCenterRuntime, RuntimeErrorState
from .updates import ControlCenterUpdates

logger = logging.getLogger(__name__)


def update_control_center(agent) -> dict:
    """Review and activate the configured Control Center build after editing it."""
    requester = (agent.current_session or {}).get('requester') or {}
    if requester.get('level') != 'admin':
        raise PermissionError('Only the verified Host administrator may update the Control Center')
    controller = getattr(agent, '_control_center', None)
    if controller is None:
        raise RuntimeErrorState('This Host has no Control Center configuration')
    claim = controller.updates._claim(time.time(), True)
    if claim is None:
        raise RuntimeErrorState('Control Center update is busy or budget-limited')
    controller.updates.execute(claim, generate=False)
    return controller.snapshot()


class ControlCenterController:
    def __init__(self, runtime, build_dir, *, author_factory, entry='index.html', capabilities=()):
        self.runtime, self.build_dir = runtime, Path(build_dir)
        self.author_factory, self.entry, self.capabilities = author_factory, entry, capabilities
        self.updates = ControlCenterUpdates(runtime, self.build_dir, generator=self._generate,
                                            entry=entry, capabilities=capabilities)
        self.tasks = set()
        self._source_revision = None

    def _generate(self, prompt):
        agent = self.author_factory()
        started = time.monotonic()
        def budget(current):
            if time.monotonic() - started > 300 or current.total_cost > 0.50:
                raise RuntimeErrorState('Control Center author turn reached its budget')
        agent.events['before_llm'].append(budget)
        # Explicit scheduled owner work, separate from any remote user's session.
        session = {'requester': {'level': 'admin', 'address': 'host-internal'},
                   'control_center_source': True}
        result = agent.input(prompt, max_iterations=8, session=session)
        return {'result': result, 'cost_usd': agent.total_cost}

    def attach(self, agent):
        agent._control_center = self
        agent.add_tool(update_control_center)
        return agent

    def snapshot(self):
        state = self.runtime.snapshot()
        history = [{key: value for key, value in item.items() if key not in {'manifest', 'event_id'}}
                   for item in state['history'][-20:]]
        updates = self.updates.snapshot()
        for name in ('pending', 'running'):
            if updates.get(name):
                updates[name] = {key: value for key, value in updates[name].items()
                                 if key not in {'event_id', 'pid'}}
        return {**state, 'history': history, 'updates': updates}

    def source(self, path, revision=None):
        validate_path(path)
        if revision is None:
            bundle = capture_bundle(self.build_dir, entry=self.entry, capabilities=self.capabilities)
            revision, manifest = bundle.revision, bundle.manifest
            if path not in bundle.files:
                raise ValueError('File is not in the current build')
            data = bundle.files[path]
        else:
            record = next((item for item in reversed(self.runtime.snapshot()['history'])
                           if item['revision'] == revision and item['status'] == 'approved'), None)
            if record is None:
                raise ValueError('Revision has no retained approval')
            manifest = record['manifest']
            asset = next((item for item in manifest['files'] if item['path'] == path), None)
            if asset is None:
                raise ValueError('File is not in this approved revision')
            data = self.runtime.uploader.source(record['app'], asset)
        if len(data) > 128 * 1024:
            raise ValueError('File is too large for Code view; open it in the project')
        try:
            content = data.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise ValueError('Binary asset; use its manifest hash') from exc
        return {'path': path, 'text': content, 'revision': revision,
                'files': [item['path'] for item in manifest['files']],
                'media_type': media_type(path)}

    def diff(self, path, base_revision, revision=None):
        before, after = self.source(path, base_revision), self.source(path, revision)
        lines = difflib.unified_diff(before['text'].splitlines(), after['text'].splitlines(),
                                     fromfile=before['revision'] + '/' + path,
                                     tofile=after['revision'] + '/' + path, lineterm='')
        result, size = [], 0
        for line in lines:
            size += len(line.encode('utf-8')) + 1
            if size > 256 * 1024:
                raise ValueError('Diff exceeds display limit; compare in the project')
            result.append(line)
        return {'path': path, 'text': '\n'.join(result), 'base_revision': before['revision'],
                'revision': after['revision']}

    async def command(self, action, payload, *, is_admin):
        if action == 'state':
            return await asyncio.to_thread(self.snapshot)
        if not is_admin:
            raise PermissionError('Control Center author controls require Host administrator access')
        if not isinstance(payload, dict):
            raise ValueError('Control Center payload must be an object')
        if action == 'source':
            return await asyncio.to_thread(self.source, payload.get('path', self.entry), payload.get('revision'))
        if action == 'diff':
            if not payload.get('base_revision'):
                raise ValueError('Choose a retained base revision')
            return await asyncio.to_thread(self.diff, payload.get('path', self.entry),
                                           payload['base_revision'], payload.get('revision'))
        if action == 'configure':
            return await asyncio.to_thread(self.updates.configure, payload)
        if action == 'rollback':
            return await asyncio.to_thread(self.runtime.rollback, payload.get('revision'))
        if action != 'update':
            raise ValueError('Unsupported Control Center command')
        claim = await asyncio.to_thread(self.updates._claim, time.time(), True)
        if claim is None:
            raise RuntimeErrorState('Control Center update is busy or budget-limited')
        task = asyncio.create_task(asyncio.to_thread(self.updates.execute, claim))
        self.tasks.add(task)
        task.add_done_callback(self._finished)
        return {'status': 'accepted', 'request_id': claim['id']}

    def _finished(self, task):
        self.tasks.discard(task)
        if not task.cancelled() and task.exception():
            logger.error('Control Center update worker failed: %s', type(task.exception()).__name__)

    async def drain(self):
        if self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)

    async def tick(self, now):
        # Detect author-file changes at the existing Host tick, never by executing
        # them. Changes generated by this controller are already the active hash.
        state = self.updates.snapshot()
        if state['enabled'] and 'control_center.source.changed' in state['events']:
            bundle = await asyncio.to_thread(capture_bundle, self.build_dir, entry=self.entry,
                                             capabilities=self.capabilities)
            active = (self.runtime.snapshot().get('active') or {}).get('revision')
            if bundle.revision != active and bundle.revision != self._source_revision:
                self.updates.enqueue('control_center.source.changed', bundle.revision, now=now.timestamp())
            self._source_revision = bundle.revision
        return await asyncio.to_thread(self.updates.tick, now=now.timestamp())

    def completed_turn(self, result, prompt):
        session = result.get('session') or {}
        if session.get('control_center_source'):
            return
        event_id = str(session.get('session_id', '')) + ':' + str(session.get('turn', ''))
        self.updates.enqueue('agent.turn.completed', event_id)
        # A slash skill turn is attributable to the user's visible skill request.
        if isinstance(prompt, str) and prompt.startswith('/'):
            self.updates.enqueue('agent.skill.completed', event_id)


def controller_from_config(config, project_dir, address, author_factory):
    if not config:
        return None
    if not isinstance(config, dict):
        raise ValueError('control_center must be an object')
    from ....environment import global_config_dir
    from ....core.usage import DEFAULT_MODEL
    from .reviewer import SkillReviewer
    from .upload import ArtifactUploader
    root = Path(project_dir).resolve()
    build = (root / config.get('build', '.co/control-center')).resolve()
    if not build.is_relative_to(root):
        raise ValueError('Control Center build must be inside its project')
    state = Path(config.get('state_dir') or global_config_dir() / 'runtime/control-centers' /
                 hashlib.sha256((address + str(root)).encode()).hexdigest()).resolve()
    if state.is_relative_to(root):
        raise ValueError('Control Center runtime state must be outside the authored project')
    reviewer = SkillReviewer(model=config.get('review_model', DEFAULT_MODEL))
    uploader = ArtifactUploader(config.get('app_id', 'home'), config['serving_domain'],
                                api_url=config.get('api_url'))
    runtime = ControlCenterRuntime(state, reviewer=reviewer, uploader=uploader,
                                   policy=reviewer.policy_id, available=uploader.available)
    controller = ControlCenterController(runtime, build, author_factory=author_factory,
        entry=config.get('entry', 'index.html'), capabilities=tuple(config.get('capabilities', [])))
    # Saved UI settings remain authoritative on restart; YAML supplies initial defaults.
    if not controller.updates.path.exists() and config.get('updates'):
        controller.updates.configure(config['updates'])
    return controller
