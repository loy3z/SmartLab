"""People: the Manager's user list, deactivation, staff accounts (invite codes, sign-in) and finding a person to book
for.
"""
import re
import secrets
from dataclasses import replace
from uuid import uuid4

from ..domain import BookingStatus, Principal, Role, StaffCredential
from ..errors import DomainError
from .base import UNDECIDED_STATUSES

_INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I, so codes are easy to read out


def new_invite_code():
    raw = "".join(secrets.choice(_INVITE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def normalize_invite_code(code):
    return re.sub(r"[^A-Z0-9]", "", (code or "").upper())


class AccountsMixin:
    def list_users(self, actor, role=None, active=None, query=None):
        self.require_manager(actor)
        query = (query or "").strip().casefold()
        users = [item for item in self.repo.list_principals()
                 if (role is None or item.role == Role(role)) and (active is None or item.active == active)
                 and (not query or query in f"{item.zid} {item.display_name} {item.university_email}".casefold())]
        return sorted(users, key=lambda item: (item.role.value, item.zid))

    def update_user(self, actor, user_id, role=None, active=None):
        """(De)activate an account. Roles are fixed when the account is created.

        Students, Admins and Managers are separate kinds of account (client, week 5): a student is never
        given a staff role (passing inductions proves lab eligibility, not employment), and Admin and Manager
        are different levels of staff that do not switch. Staff accounts come from Add staff (create_staff)
        or, later, from the university identity provider; to replace someone, add the new account and
        deactivate the old one. ``role`` is accepted only when it equals the current role.
        Deactivating a student rejects their undecided requests at once; approved bookings are kept for
        the Manager to review.
        """
        self.require_manager(actor)
        if role is None and active is None:
            raise DomainError("VALIDATION_ERROR", "Provide role and/or active.")
        user_id = str(user_id)
        if user_id == actor.id:
            raise DomainError("SELF_MODIFICATION_FORBIDDEN", "Managers cannot change their own role or status.", 403)
        managers = [item.id for item in self.repo.list_principals() if item.role == Role.MANAGER]
        with self.repo.atomic(student_ids=sorted(set(managers + [user_id]))):
            current = self.repo.get_principal(user_id)
            if current is None:
                raise DomainError("NOT_FOUND", "User not found.", 404)
            if role is not None and Role(role) != current.role:
                raise DomainError("ROLE_CHANGE_NOT_ALLOWED",
                                  "Roles are fixed when an account is created. Students, Admins and Managers are "
                                  "separate accounts: add a new staff account with Add staff and deactivate the "
                                  "old one if needed.", 409,
                                  {"zid": current.zid, "role": current.role.value})
            updated = replace(current, role=Role(role) if role is not None else current.role,
                              active=current.active if active is None else active)
            if updated == current:
                return current
            if not any(item.role == Role.MANAGER and item.active
                       for item in [updated] + [p for p in self.repo.list_principals() if p.id != user_id]):
                raise DomainError("LAST_MANAGER", "At least one active Manager must remain.", 409)
            self.repo.save_principal(updated)
            self._audit(actor.id, "USER_UPDATED", "principal", updated.id, zid=updated.zid,
                        previous_role=current.role.value, role=updated.role.value,
                        previous_active=current.active, active=updated.active)
        if current.active and not updated.active:
            self._reject_undecided_requests(updated.id, actor.id, "ACCOUNT_DEACTIVATED",
                                            "The account was deactivated.")
        return updated

    def _reject_undecided_requests(self, student_id, actor_id, reason_code, note):
        """Reject a person's undecided requests (pending and waitlisted) and pass the time on."""
        changed = []
        for booking in sorted(self.repo.list_bookings(student_id=student_id), key=lambda item: (item.created_at, item.id)):
            if booking.status not in UNDECIDED_STATUSES:
                continue
            with self.repo.atomic(resource_ids=[booking.resource_id], student_ids=[student_id]):
                current = self.repo.get_booking(booking.id)
                if current.status not in UNDECIDED_STATUSES:
                    continue
                revised = replace(current, status=BookingStatus.REJECTED, reason_code=reason_code, reviewed_by=actor_id,
                                  reviewed_at=self.now(), decision_reason=note, updated_at=self.now())
                self._save_booking(revised)
                self._audit(actor_id, "BOOKING_REJECTED", "booking", revised.id, reason=note, reason_code=reason_code)
                changed.append(revised)
                self._promote_waitlist(revised.resource_id)
        return changed

    def create_staff(self, actor, zid, display_name, university_email, role=Role.MANAGER):
        """Manager only ("Add staff"): create an Admin or Manager account for a staff member.

        Staff are not promoted from student accounts. With university SSO, the identity provider would
        create these from its staff records instead; the role is still assigned here by a Manager.
        """
        self.require_manager(actor)
        return self._create_staff_account(actor.id, zid, display_name, university_email, role)

    def bootstrap_manager(self, zid, display_name, university_email):
        """Sprint 3: create a Manager from the server command line (manage.py create_manager), e.g. the first one.

        Same rules as Add staff; the audit records SYSTEM as the actor. Returns (manager, invite code).
        """
        created = self._create_staff_account("SYSTEM", zid, display_name, university_email, Role.MANAGER)
        return created, self.repo.get_credential(created.id).invite_code

    def _create_staff_account(self, actor_id, zid, display_name, university_email, role):
        """Shared by Add staff and bootstrap_manager: check the details, save the account and its invite code."""
        role = Role(role)
        if role not in (Role.ADMIN, Role.MANAGER):
            raise DomainError("VALIDATION_ERROR", "Staff accounts are ADMIN or MANAGER.")
        zid = zid.strip().lower()
        if not re.fullmatch(r"z\d{7}", zid):
            raise DomainError("VALIDATION_ERROR", "zID must be 'z' followed by 7 digits.")
        display_name, university_email = display_name.strip(), university_email.strip()
        if not display_name:
            raise DomainError("VALIDATION_ERROR", "A display name is required.")
        with self.repo.atomic():
            existing = next((item for item in self.repo.list_principals() if item.zid == zid), None)
            if existing:
                raise DomainError("USER_EXISTS", "A user with this zID already exists.", 409, {"user_id": existing.id})
            try:
                created = Principal(str(uuid4()), zid, display_name, role, university_email)
            except ValueError as exc:
                raise DomainError("VALIDATION_ERROR", str(exc)) from exc
            self.repo.save_principal(created)
            # The new staff member activates the account on the staff sign-in page with this code.
            self.repo.save_credential(StaffCredential(created.id, invite_code=new_invite_code(), updated_at=self.now()))
            self._audit(actor_id, f"{role.value}_CREATED", "principal", created.id, zid=zid)
            return created

    def staff_access(self, user):
        """For the user list: whether a staff account is activated, and its invite code while it is not."""
        if not user.is_staff:
            return {"activation_status": None, "invite_code": None}
        credential = self.repo.get_credential(user.id)
        if credential and credential.activated:
            return {"activation_status": "ACTIVATED", "invite_code": None}
        return {"activation_status": "AWAITING_ACTIVATION", "invite_code": credential.invite_code if credential else None}

    def reset_staff_access(self, actor, user_id):
        """Manager only: clear a staff member's password and issue a new invite code (forgotten password,
        or a lost code). The role and history stay the same."""
        self.require_manager(actor)
        user_id = str(user_id)
        if user_id == actor.id:
            raise DomainError("SELF_MODIFICATION_FORBIDDEN", "Ask another Manager to reset your access.", 403)
        with self.repo.atomic(student_ids=[user_id]):
            user = self.repo.get_principal(user_id)
            if user is None:
                raise DomainError("NOT_FOUND", "User not found.", 404)
            if not user.is_staff:
                raise DomainError("STUDENT_USES_SSO", "Students sign in with university sign-in and have no password here.", 409)
            self.repo.save_credential(StaffCredential(user.id, invite_code=new_invite_code(), updated_at=self.now()))
            self._audit(actor.id, "STAFF_ACCESS_RESET", "principal", user.id, zid=user.zid)
        return user

    def _staff_by_zid(self, zid):
        zid = (zid or "").strip().lower()
        return next((item for item in self.repo.list_principals() if item.zid == zid), None)

    def activate_staff(self, zid, invite_code, password):
        """First staff sign-in: the invite code from the Manager plus a password the staff member chooses."""
        from django.contrib.auth.hashers import make_password
        if len(password or "") < 8:
            raise DomainError("VALIDATION_ERROR", "Choose a password of at least 8 characters.", 400, {"password": ["At least 8 characters."]})
        with self.repo.atomic():
            user = self._staff_by_zid(zid)
            credential = self.repo.get_credential(user.id) if user and user.is_staff else None
            if (credential is None or not credential.invite_code
                    or normalize_invite_code(credential.invite_code) != normalize_invite_code(invite_code)):
                raise DomainError("INVALID_INVITE_CODE", "The zID or invite code is not correct. Ask your Manager for a new code.", 400)
            if not user.active:
                raise DomainError("ACCOUNT_DEACTIVATED", "This account has been deactivated.", 403)
            self.repo.save_credential(StaffCredential(user.id, password_hash=make_password(password), updated_at=self.now()))
            self._audit(user.id, "STAFF_ACTIVATED", "principal", user.id, zid=user.zid)
        return user

    def staff_sign_in(self, zid, password):
        """Staff sign-in page. The role comes from the account, never from the page used."""
        from django.contrib.auth.hashers import check_password
        user = self._staff_by_zid(zid)
        if user is not None and not user.is_staff:
            raise DomainError("STUDENT_USES_SSO", "Students sign in with university sign-in on the main sign-in page.", 403)
        if user is None:
            raise DomainError("INVALID_CREDENTIALS", "The zID or password is not correct.", 401)
        if not user.active:
            raise DomainError("ACCOUNT_DEACTIVATED", "This account has been deactivated.", 403)
        credential = self.repo.get_credential(user.id)
        if credential is None or not credential.activated:
            raise DomainError("ACCOUNT_NOT_ACTIVATED", "Activate your account first with the invite code from your Manager.", 403)
        if not check_password(password or "", credential.password_hash):
            raise DomainError("INVALID_CREDENTIALS", "The zID or password is not correct.", 401)
        return user

    def change_password(self, actor, current_password, new_password):
        """Sprint 3: a signed-in Admin or Manager changes their own password (the current one is required).

        Students have no password here: they use university sign-in.
        """
        from django.contrib.auth.hashers import check_password, make_password
        if not actor.is_staff:
            raise DomainError("STUDENT_USES_SSO", "Students sign in with university sign-in and have no SmartLab password.", 403)
        if len(new_password or "") < 8:
            raise DomainError("VALIDATION_ERROR", "Choose a password of at least 8 characters.", 400,
                              {"new_password": ["At least 8 characters."]})
        with self.repo.atomic(student_ids=[actor.id]):
            credential = self.repo.get_credential(actor.id)
            if credential is None or not credential.activated or not check_password(current_password or "", credential.password_hash):
                raise DomainError("INVALID_CREDENTIALS", "The current password is not correct.", 400,
                                  {"current_password": ["Not correct."]})
            if check_password(new_password, credential.password_hash):
                raise DomainError("VALIDATION_ERROR", "Choose a password different from the current one.", 400,
                                  {"new_password": ["Same as the current password."]})
            self.repo.save_credential(replace(credential, password_hash=make_password(new_password), updated_at=self.now()))
            self._audit(actor.id, "STAFF_PASSWORD_CHANGED", "principal", actor.id)

    def create_manager(self, actor, zid, display_name, university_email):
        return self.create_staff(actor, zid, display_name, university_email, Role.MANAGER)

    def find_person(self, actor, zid):
        """Admin/Manager: find the active account to book for by zID (Book on behalf of someone)."""
        self.require_staff(actor)
        zid = str(zid or "").strip().lower()
        if not re.fullmatch(r"z\d{7}", zid):
            raise DomainError("VALIDATION_ERROR", "zID must be z followed by 7 digits.")
        person = next((item for item in self.repo.list_principals() if item.zid == zid), None)
        if person is None:
            raise DomainError("PERSON_NOT_FOUND", f"No account found for {zid}.", 404, {"zid": zid})
        if not person.active:
            raise DomainError("ACCOUNT_INACTIVE", f"{zid}'s account is deactivated.", 409, {"zid": zid})
        return person

    def _beneficiary(self, actor, on_behalf_of_zid):
        """The person a request is for: the actor, or (Admin/Manager only) the active account with that zID."""
        if not on_behalf_of_zid:
            return actor
        if actor.role not in (Role.ADMIN, Role.MANAGER):
            raise DomainError("FORBIDDEN", "Only Admins and Managers can book on behalf of someone else.", 403)
        return self.find_person(actor, on_behalf_of_zid)
