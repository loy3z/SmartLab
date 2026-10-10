"""Composition root: replace factories without changing HTTP or booking policy."""
from datetime import UTC, datetime, timedelta
from threading import RLock
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string
from .domain import Principal, QualificationRequirement, QualificationStatus, QualificationSubmission, Resource, ResourceKind, Role
from .services import BookingService
from .calendar_sync import CalendarSyncService

_service = None
_lock = RLock()

def fixed_id(number):
    return f"00000000-0000-0000-0000-{number:012d}"

# Prototype data requested by the client: about 2 labs and 20 example devices.
# Each device is its own bookable resource with its own availability (not a stock count).
# (id number, name, kind, location, needs advanced training)
DEMO_RESOURCES = [
    (101, "Lab Room 1", ResourceKind.ROOM, "Demo laboratory", False),
    (102, "Lab Room 2", ResourceKind.ROOM, "Demo laboratory", True),
    (201, "Microscope 001", ResourceKind.EQUIPMENT, "Lab Room 1", False),
    (202, "Camera 001", ResourceKind.EQUIPMENT, "Lab Room 2", True),
    (203, "Microscope 002", ResourceKind.EQUIPMENT, "Lab Room 1", False),
    (204, "Oscilloscope 001", ResourceKind.EQUIPMENT, "Lab Room 1", False),
    (205, "Oscilloscope 002", ResourceKind.EQUIPMENT, "Lab Room 1", False),
    (206, "Signal Generator 001", ResourceKind.EQUIPMENT, "Lab Room 1", False),
    (207, "Bench Power Supply 001", ResourceKind.EQUIPMENT, "Lab Room 1", False),
    (208, "Bench Power Supply 002", ResourceKind.EQUIPMENT, "Lab Room 1", False),
    (209, "Digital Multimeter 001", ResourceKind.EQUIPMENT, "Lab Room 1", False),
    (210, "Digital Multimeter 002", ResourceKind.EQUIPMENT, "Lab Room 1", False),
    (211, "Soldering Station 001", ResourceKind.EQUIPMENT, "Lab Room 1", False),
    (212, "Soldering Station 002", ResourceKind.EQUIPMENT, "Lab Room 1", False),
    (213, "Logic Analyser 001", ResourceKind.EQUIPMENT, "Lab Room 1", False),
    (214, "3D Printer 001", ResourceKind.EQUIPMENT, "Lab Room 2", True),
    (215, "Laser Cutter 001", ResourceKind.EQUIPMENT, "Lab Room 2", True),
    (216, "Spectrometer 001", ResourceKind.EQUIPMENT, "Lab Room 2", True),
    (217, "Centrifuge 001", ResourceKind.EQUIPMENT, "Lab Room 2", True),
    (218, "Thermal Camera 001", ResourceKind.EQUIPMENT, "Lab Room 2", True),
    (219, "Fume Extractor 001", ResourceKind.EQUIPMENT, "Lab Room 1", False),
    (220, "Data Logger 001", ResourceKind.EQUIPMENT, "Lab Room 1", False),
]

def seed_demo_data(service):
    requirement = QualificationRequirement(fixed_id(1), "General laboratory induction", "Demo requirement; replace with client-approved training rules.")
    service.repo.save_requirement(requirement)
    advanced = QualificationRequirement(fixed_id(2), "Advanced laboratory training", "Separate prerequisite for Lab Room 2 and its specialist devices.")
    service.repo.save_requirement(advanced)
    for number, name, kind, location, needs_advanced in DEMO_RESOURCES:
        service.repo.save_resource(Resource(fixed_id(number), name, kind, location, "Single resource; demonstration data.",
            required_qualification_id=advanced.id if needs_advanced else requirement.id,
            pending_hold_minutes=settings.DEFAULT_PENDING_HOLD_MINUTES))
    for number, zid, name, role in [(501, "z1000001", "Qualified demo student", Role.STUDENT),
                                    (502, "z1000002", "New demo student", Role.STUDENT),
                                    (901, "z9000001", "Demo administrator", Role.ADMIN),
                                    (902, "z9000002", "Demo manager", Role.MANAGER)]:
        service.repo.save_principal(Principal(fixed_id(number), zid, name, role, f"{zid}@ad.unsw.edu.au"))
    now = service.now()
    evidence = service.storage.save(b"%PDF-1.4\nDemo seeded induction evidence\n%%EOF", "demo-induction.pdf", "application/pdf", fixed_id(501))
    service.repo.save_submission(QualificationSubmission(fixed_id(601), fixed_id(501), requirement.id, "Seeded demo induction", "Development fixture", evidence.id, now,
                                                        status=QualificationStatus.VERIFIED, reviewed_by=fixed_id(901), reviewed_at=now,
                                                        valid_until=service.qualification_expiry(now)))

def get_service():
    global _service
    with _lock:
        if _service is None:
            repo = import_string(settings.REPOSITORY_FACTORY)()
            storage = import_string(settings.FILE_STORAGE_FACTORY)()
            from .repository import MemoryRepository
            from .storage import MemoryFileStorage
            if not settings.DEBUG and (isinstance(repo, MemoryRepository) or isinstance(storage, MemoryFileStorage)):
                raise ImproperlyConfigured("Configure durable repository and private file-storage adapters outside DEBUG mode.")
            _service = BookingService(repo, storage, wait_hours=settings.APPROVAL_WAIT_HOURS,
                                      qualification_validity_days=settings.QUALIFICATION_VALIDITY_DAYS)
            _service.calendar_sync = CalendarSyncService(repo, import_string(settings.OUTLOOK_PROVIDER_FACTORY)(),
                enabled=settings.OUTLOOK_ENABLED, clock=lambda: _service.now())
            if settings.SEED_DEMO_DATA:
                seed_demo_data(_service)
        return _service

def reset_runtime():
    """Test-only reset; deliberately not exposed as an HTTP endpoint."""
    global _service
    with _lock:
        _service = None
    return get_service()
