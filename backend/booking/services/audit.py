"""Audit trail query for Admins and Managers."""
from ..errors import DomainError


class AuditMixin:

    AUDIT_ENTITY_TYPES = ("booking", "qualification", "resource", "principal", "requirement")

    def audit_trail(self, actor, resource_id=None, student_id=None, entity_type=None, entity_id=None,
                    action=None, actor_id=None, since=None, until=None, limit=100, offset=0):
        """Admin/Manager view of requests, approvals, changes and cancellations, newest first.

        resource_id matches the resource's own records and those of its bookings; student_id
        matches records the student performed plus their bookings, submissions and account.
        Returns (total_matching, page). Filtering runs in memory over ``repo.list_audit()``;
        a database adapter may push these filters into an indexed query with the same results.
        """
        self.require_staff(actor)
        if entity_type is not None and entity_type not in self.AUDIT_ENTITY_TYPES:
            raise DomainError("VALIDATION_ERROR", "Unknown audit entity type.")
        for name, value in (("since", since), ("until", until)):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise DomainError("INVALID_TIME", f"{name} requires a UTC offset.")
        if since is not None and until is not None and since >= until:
            raise DomainError("INVALID_TIME", "since must be earlier than until.")
        if not 1 <= limit <= 500 or offset < 0:
            raise DomainError("VALIDATION_ERROR", "Use limit 1-500 and a non-negative offset.")
        resource_entities = student_entities = None
        if resource_id is not None:
            resource_id = str(resource_id)
            resource_entities = {("resource", resource_id)} | {
                ("booking", item.id) for item in self.repo.list_bookings(resource_id=resource_id)}
        if student_id is not None:
            student_id = str(student_id)
            student_entities = ({("principal", student_id)}
                                | {("booking", item.id) for item in self.repo.list_bookings(student_id=student_id)}
                                | {("qualification", item.id) for item in self.repo.list_submissions(student_id=student_id)})
        matches = []
        for index, record in enumerate(self.repo.list_audit()):
            key = (record.entity_type, record.entity_id)
            if resource_entities is not None and key not in resource_entities:
                continue
            if student_entities is not None and key not in student_entities and record.actor_id != student_id:
                continue
            if entity_type is not None and record.entity_type != entity_type:
                continue
            if entity_id is not None and record.entity_id != str(entity_id):
                continue
            if action is not None and record.action != action:
                continue
            if actor_id is not None and record.actor_id != str(actor_id):
                continue
            if since is not None and record.at < since:
                continue
            if until is not None and record.at >= until:
                continue
            matches.append((record.at, index, record))
        matches.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return len(matches), [record for _, _, record in matches[offset:offset + limit]]
