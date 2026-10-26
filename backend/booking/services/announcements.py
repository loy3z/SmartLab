"""Sprint 3 (1.19.0): attributed public announcements, separate from personal notifications."""
from dataclasses import replace
from uuid import uuid4

from ..domain import Announcement, ResourceStatus, Role
from ..errors import DomainError


class AnnouncementsMixin:
    def list_announcements(self, actor, include_ended=False):
        if include_ended:
            self.require_staff(actor)
        now = self.now()
        return [item for item in self.repo.list_announcements() if include_ended or
                (item.removed_at is None and (item.expires_at is None or item.expires_at > now))]

    def _announcement(self, announcement_id):
        item = self.repo.get_announcement(str(announcement_id))
        if item is None:
            raise DomainError('NOT_FOUND', 'Announcement not found.', 404)
        return item

    def _announcement_fields(self, title, body):
        title, body = title.strip(), body.strip()
        if not 1 <= len(title) <= 120 or not 1 <= len(body) <= 1000:
            raise DomainError('VALIDATION_ERROR', 'Use a title of 1–120 characters and a message of 1–1000 characters.')
        return title, body

    def _check_removal_time(self, expires_at):
        # Review 1.19.0 R1: a past removal time would publish an announcement that no home page shows.
        if expires_at is not None and expires_at <= self.now():
            raise DomainError('VALIDATION_ERROR', 'Choose a removal time in the future, or leave it blank.')

    def create_announcement(self, actor, title, body, expires_at=None):
        self.require_staff(actor)
        title, body = self._announcement_fields(title, body)
        self._check_removal_time(expires_at)
        with self.repo.atomic():
            item = Announcement(str(uuid4()), title, body, 'MANUAL', None, actor.id, self.now(),
                                expires_at=expires_at, updated_at=self.now(), author_role=actor.role.value)
            self.repo.save_announcement(item)
            self._audit(actor.id, 'ANNOUNCEMENT_CREATED', 'announcement', item.id)
            return item

    def update_announcement(self, actor, announcement_id, changes):
        self.require_staff(actor)
        with self.repo.atomic():
            item = self._announcement(announcement_id)
            if item.kind != 'MANUAL' or actor.id != item.created_by:
                raise DomainError('FORBIDDEN', 'Only the author can edit a manual announcement.', 403)
            if item.removed_at is not None:
                raise DomainError('ANNOUNCEMENT_REMOVED', 'This announcement has been removed.', 409)
            if not changes or set(changes) - {'title', 'body', 'expires_at'}:
                raise DomainError('VALIDATION_ERROR', 'Provide a title, message or expiry date.')
            title, body = self._announcement_fields(changes.get('title', item.title), changes.get('body', item.body))
            if 'expires_at' in changes:
                self._check_removal_time(changes['expires_at'])
            updated = replace(item, title=title, body=body, expires_at=changes.get('expires_at', item.expires_at), updated_at=self.now())
            self.repo.save_announcement(updated)
            self._audit(actor.id, 'ANNOUNCEMENT_UPDATED', 'announcement', item.id)
            return updated

    def remove_announcement(self, actor, announcement_id):
        self.require_staff(actor)
        with self.repo.atomic():
            item = self._announcement(announcement_id)
            if item.kind != 'MANUAL' or (actor.id != item.created_by and actor.role != Role.MANAGER):
                raise DomainError('FORBIDDEN', 'Only the author or a Manager can remove a manual announcement.', 403)
            if item.removed_at is None:
                item = replace(item, removed_at=self.now(), removed_by=actor.id, updated_at=self.now())
                self.repo.save_announcement(item)
                self._audit(actor.id, 'ANNOUNCEMENT_REMOVED', 'announcement', item.id)
            return item

    def _status_announcement(self, actor, resource, expected_back=None):
        """Only set_resource_status calls this, inside its existing resource transaction.

        Expected back is an estimate, never an expiry or an instruction to reopen the resource.
        A status announcement cannot be edited/removed through the manual-announcement endpoints.
        """
        previous = next((item for item in self.repo.list_announcements()
                         if item.kind == 'RESOURCE_STATUS' and item.resource_id == resource.id and item.removed_at is None), None)
        now = self.now()
        if resource.status == ResourceStatus.AVAILABLE:
            if previous:
                self.repo.save_announcement(replace(previous, removed_at=now, removed_by=actor.id, updated_at=now))
                self._audit(actor.id, 'STATUS_ANNOUNCEMENT_REMOVED', 'announcement', previous.id)
            return
        suffix = ' is under maintenance' if resource.status == ResourceStatus.MAINTENANCE else ' is closed'
        title = resource.name[:120 - len(suffix)] + suffix
        if previous:
            item = replace(previous, title=title, body=resource.status_reason or '', expected_back=expected_back,
                           created_by=actor.id, author_role=actor.role.value, updated_at=now)
        else:
            item = Announcement(str(uuid4()), title, resource.status_reason or '', 'RESOURCE_STATUS', resource.id,
                                actor.id, now, updated_at=now, author_role=actor.role.value, expected_back=expected_back)
        if item != previous:
            self.repo.save_announcement(item)
            self._audit(actor.id, 'STATUS_ANNOUNCEMENT_UPDATED' if previous else 'STATUS_ANNOUNCEMENT_CREATED',
                        'announcement', item.id, resource_id=resource.id)
