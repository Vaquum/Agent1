from __future__ import annotations

from agent1.core.contracts import CommentTarget
from agent1.core.contracts import CommentTargetType
from agent1.core.ingress_contracts import IngressEventType
from agent1.core.ingress_contracts import NormalizedIngressEvent


class CommentRoutingError(ValueError):
    pass


def _get_str(details: dict[str, object], key: str) -> str:
    value = details.get(key)
    if isinstance(value, str):
        return value

    return ''


def _get_int(details: dict[str, object], key: str) -> int | None:
    value = details.get(key)
    if isinstance(value, int):
        return value

    return None


class CommentRouter:
    def __init__(
        self,
        require_review_thread_reply: bool,
        allow_top_level_pr_fallback: bool,
    ) -> None:
        self._require_review_thread_reply = require_review_thread_reply
        self._allow_top_level_pr_fallback = allow_top_level_pr_fallback

    def _route_pr_review_comment(self, normalized_event: NormalizedIngressEvent) -> CommentTarget:
        is_review_thread_comment = bool(normalized_event.details.get('is_review_thread_comment', False))
        if is_review_thread_comment is False:
            return CommentTarget(
                target_type=CommentTargetType.PR,
                pr_number=normalized_event.entity_number,
            )

        review_comment_id = _get_int(normalized_event.details, 'review_comment_id')
        path = _get_str(normalized_event.details, 'path')
        line = _get_int(normalized_event.details, 'line')
        side = _get_str(normalized_event.details, 'side')
        thread_id = _get_str(normalized_event.details, 'thread_id')
        if thread_id == '' and review_comment_id is not None:
            thread_id = str(review_comment_id)

        has_thread_metadata = (
            review_comment_id is not None
            and path != ''
            and line is not None
            and side != ''
            and thread_id != ''
        )
        if has_thread_metadata:
            return CommentTarget(
                target_type=CommentTargetType.PR_REVIEW_THREAD,
                pr_number=normalized_event.entity_number,
                thread_id=thread_id,
                review_comment_id=review_comment_id,
                path=path,
                line=line,
                side=side,
            )

        if self._require_review_thread_reply and self._allow_top_level_pr_fallback is False:
            message = f'Missing thread metadata for review comment routing: {normalized_event.entity_key}'
            raise CommentRoutingError(message)

        return CommentTarget(
            target_type=CommentTargetType.PR,
            pr_number=normalized_event.entity_number,
        )

    def route(self, normalized_event: NormalizedIngressEvent) -> CommentTarget:

        '''
        Create deterministic comment target from normalized ingress event payload.

        Args:
        normalized_event (NormalizedIngressEvent): Normalized ingress event payload.

        Returns:
        CommentTarget: Deterministic comment target contract.
        '''

        ingress_event_type = str(normalized_event.details.get('ingress_event_type', ''))
        if ingress_event_type in {
            IngressEventType.ISSUE_MENTION.value,
            IngressEventType.ISSUE_UPDATED.value,
            IngressEventType.ISSUE_ASSIGNMENT.value,
        }:
            return CommentTarget(
                target_type=CommentTargetType.ISSUE,
                issue_number=normalized_event.entity_number,
            )
        if ingress_event_type == IngressEventType.PR_MENTION.value:
            return CommentTarget(
                target_type=CommentTargetType.PR,
                pr_number=normalized_event.entity_number,
            )
        if ingress_event_type == IngressEventType.PR_REVIEW_COMMENT.value:
            return self._route_pr_review_comment(normalized_event)

        message = f'Unsupported comment routing event type: {ingress_event_type}'
        raise CommentRoutingError(message)


__all__ = ['CommentRouter', 'CommentRoutingError']
