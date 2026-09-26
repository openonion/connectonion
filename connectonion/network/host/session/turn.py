"""Claim, run and persist one session turn for any ingress."""

import copy
import logging
import time
from typing import Callable

from ....core.mode import AUTO, READ_ONLY, mode_of, set_mode
from .mode import HostPermissionPolicy, ModeTransactionError, claim_host_prompt
from .storage import SessionStorage
from .ui import session_to_chat_items

logger = logging.getLogger(__name__)


def input_handler(create_agent: Callable, storage: SessionStorage, prompt: str, result_ttl: int,
                  session: dict | None = None, connection=None, images: list[str] | None = None,
                  files: list[dict] | None = None, requester: dict | None = None,
                  mode_policy: HostPermissionPolicy | None = None,
                  is_admin: bool = False, watch_event: dict | None = None) -> dict:
    """POST /input (and WebSocket /ws) with session merge and UI conversion."""
    session = session or {}
    session_id = session.get('session_id')
    if not session_id:
        raise ValueError("session_id required in session dict")
    prior_mode = mode_of(session) if watch_event is not None else None

    # Preserve the legacy internal/scheduler order when no Host policy is in
    # play. Network routes always pass a policy and must claim before factory
    # side effects; standalone callers historically construct first.
    agent = create_agent() if mode_policy is None else None
    record, server_newer = claim_host_prompt(
        storage,
        session_id,
        prompt,
        result_ttl,
        session,
        requester=requester,
        policy=mode_policy,
        is_admin=is_admin,
        force_read_only=watch_event is not None,
    )
    # claim_host_prompt() atomically rechecks the verified owner and replaces
    # every SERVER_OWNED_SESSION_KEYS value with the durable server snapshot.
    # This is the OIP successor to the 1.6.11 merge-and-restore guard.
    session = record.session

    start = time.time()
    try:
        if agent is None:
            agent = create_agent()
        agent.io = connection
        agent.storage = storage
        if mode_policy is not None:
            if hasattr(agent, "_full_access_turns"):
                agent._full_access_turns = None
            if hasattr(agent, "_full_access_needs_activation"):
                agent._full_access_needs_activation = False
            agent._host_full_access_turns_ceiling = mode_policy.full_access_turns

        input_options = {"session": session, "images": images, "files": files}
        if watch_event is not None:
            input_options["_watch_event"] = watch_event
        result = agent.input(prompt, **input_options)
        duration_ms = int((time.time() - start) * 1000)

        if watch_event is not None:
            set_mode(agent.current_session,
                     READ_ONLY if prior_mode == READ_ONLY else AUTO)
        if mode_policy is not None:
            agent.current_session = _normalized_host_result(
                agent.current_session,
                requester=requester,
                mode_policy=mode_policy,
                is_admin=is_admin,
            )

        agent.current_session['updated'] = time.time()

        record.status = "done"
        record.result = result
        record.duration_ms = duration_ms
        record.session = agent.current_session
        watch_store = getattr(agent, "_watch_store", None)
        if watch_store is not None:
            expiry = watch_store.latest_expiry(session_id)
            if expiry is not None:
                record.expires = max(record.expires or 0, expiry)
        storage.save(record)
    except Exception:
        # The claim is already durable. Always terminate it so a factory/model
        # exception cannot leave this session busy until Host restarts.
        record.status = "failed"
        record.duration_ms = int((time.time() - start) * 1000)
        if mode_policy is not None:
            record.session = _normalized_host_result(
                record.session,
                requester=requester,
                mode_policy=mode_policy,
                is_admin=is_admin,
            )
        watch_store = getattr(agent, "_watch_store", None)
        if watch_store is not None:
            expiry = watch_store.latest_expiry(session_id)
            if expiry is not None:
                record.expires = max(record.expires or 0, expiry)
        try:
            storage.save(record)
        except Exception:
            logger.exception(
                "Unable to persist failed Host prompt %s", session_id
            )
        raise

    chat_items = session_to_chat_items(agent.current_session)

    return {
        "session_id": session_id,
        "status": "done",
        "result": result,
        "duration_ms": duration_ms,
        "session": agent.current_session,
        "chat_items": chat_items,
        "server_newer": server_newer,
    }


def _normalized_host_result(
    session: dict,
    *,
    requester: dict | None,
    mode_policy: HostPermissionPolicy,
    is_admin: bool,
) -> dict:
    """Restore verified identity and fail invalid Agent mode state to Auto."""
    final_session = copy.deepcopy(session)
    if requester is not None:
        final_session["requester"] = copy.deepcopy(requester)
    else:
        final_session.pop("requester", None)
    try:
        return mode_policy.normalized(final_session, is_admin=is_admin)
    except ModeTransactionError:
        logger.exception(
            "Agent produced invalid Host session mode; resetting to auto"
        )
        return mode_policy.apply(
            final_session, AUTO, is_admin=is_admin
        )
