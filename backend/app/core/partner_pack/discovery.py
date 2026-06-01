"""Discover partner packs — via pip entry-points and via the repo ``packs/`` dir.

A partner pack registers via the entry-point group
``openconstructionerp.partner_packs``::

    [project.entry-points."openconstructionerp.partner_packs"]
    batimatech-ca = "openconstructionerp_batimatech_ca:MANIFEST"

The value must point at a module-level attribute that is either:
  * a ``PartnerPackManifest`` instance, OR
  * a ``dict`` the loader coerces into one.

In addition to pip-installed packs, ``discover_packs()`` also scans the
monorepo ``packs/`` directory so that source-checkout packs are listable on
the /modules page WITHOUT being pip-installed. Filesystem-discovered packs are
listable but are NEVER auto-activated — only an explicit ``OE_PARTNER_PACK``
env var activates a pack (see ``get_active_pack``).

At boot, ``discover_packs()`` enumerates every source. ``get_active_pack()``
picks one based on the precedence:

  1. env var ``OE_PARTNER_PACK`` (matches manifest.slug)
  2. None  — the platform runs in vanilla OCERP mode
"""

from __future__ import annotations

import importlib.util
import logging
import os
from functools import lru_cache
from importlib import resources
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path

from app.core.partner_pack.manifest import PartnerPackManifest

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "openconstructionerp.partner_packs"

# Repo root is five levels up from this file:
#   backend/app/core/partner_pack/discovery.py -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[4]
_PACKS_DIR = _REPO_ROOT / "packs"


def _coerce_manifest(value: object) -> PartnerPackManifest:
    """Accept either a manifest instance or a dict and return a manifest."""
    if isinstance(value, PartnerPackManifest):
        return value
    if isinstance(value, dict):
        return PartnerPackManifest(**value)
    raise TypeError(
        f"Partner pack entry-point must point at a PartnerPackManifest or dict, "
        f"got {type(value).__name__}"
    )


def _load_one(ep: EntryPoint) -> PartnerPackManifest | None:
    """Resolve a single entry-point into a manifest, logging failures."""
    try:
        target = ep.load()
        return _coerce_manifest(target)
    except Exception as exc:  # noqa: BLE001 — boot-time best-effort
        logger.warning(
            "Partner pack '%s' failed to load: %s. Skipping.",
            ep.name,
            exc,
            exc_info=True,
        )
        return None


def _discover_entrypoint_packs() -> list[PartnerPackManifest]:
    """Return all packs registered via the pip entry-point group."""
    try:
        eps = entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:
        # Python 3.9 fallback (the codebase requires 3.12 but be defensive).
        eps = entry_points().get(ENTRY_POINT_GROUP, [])  # type: ignore[assignment]

    manifests: list[PartnerPackManifest] = []
    for ep in eps:
        manifest = _load_one(ep)
        if manifest:
            manifests.append(manifest)
    return manifests


def _load_manifest_from_file(manifest_path: Path) -> PartnerPackManifest | None:
    """Import a pack ``manifest.py`` by file path and read its ``MANIFEST``.

    Uses a unique synthetic module name so the import never collides with
    other packs (or a pip-installed copy of the same pack) in ``sys.modules``.
    """
    # The package dir is the parent of manifest.py, e.g.
    #   packs/<slug>/src/openconstructionerp_<pkg>/manifest.py
    pkg_dir = manifest_path.parent
    synthetic_name = f"_oe_fs_pack_{pkg_dir.name}"
    try:
        spec = importlib.util.spec_from_file_location(synthetic_name, manifest_path)
        if spec is None or spec.loader is None:
            logger.warning(
                "Could not build import spec for partner pack manifest %s. Skipping.",
                manifest_path,
            )
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        manifest = getattr(module, "MANIFEST", None)
        if manifest is None:
            logger.warning(
                "Partner pack manifest %s has no MANIFEST attribute. Skipping.",
                manifest_path,
            )
            return None
        return _coerce_manifest(manifest)
    except Exception as exc:  # noqa: BLE001 — best-effort filesystem scan
        logger.warning(
            "Filesystem partner pack at %s failed to load: %s. Skipping.",
            manifest_path,
            exc,
            exc_info=True,
        )
        return None


def _discover_filesystem_packs() -> list[PartnerPackManifest]:
    """Scan the repo ``packs/`` dir for source-checkout packs.

    Looks for ``packs/<slug>/src/openconstructionerp_*/manifest.py``. Packs
    whose package dir contains a ``DEPRECATED.txt`` (anywhere under the pack)
    are skipped. Returns ``[]`` if the ``packs/`` dir does not exist.
    """
    if not _PACKS_DIR.is_dir():
        return []

    manifests: list[PartnerPackManifest] = []
    for pack_dir in sorted(_PACKS_DIR.iterdir()):
        if not pack_dir.is_dir():
            continue
        # Skip deprecated packs (a DEPRECATED.txt anywhere inside the pack).
        if any(pack_dir.rglob("DEPRECATED.txt")):
            continue
        src_dir = pack_dir / "src"
        if not src_dir.is_dir():
            continue
        for pkg_dir in sorted(src_dir.glob("openconstructionerp_*")):
            manifest_path = pkg_dir / "manifest.py"
            if not manifest_path.is_file():
                continue
            manifest = _load_manifest_from_file(manifest_path)
            if manifest:
                manifests.append(manifest)
    return manifests


@lru_cache(maxsize=1)
def discover_packs() -> list[PartnerPackManifest]:
    """Return all discoverable packs (pip entry-points + repo ``packs/`` dir).

    Entry-point packs take precedence on slug collision. Results are deduped
    by slug and sorted alphabetically. Cached for the lifetime of the process;
    call ``discover_packs.cache_clear()`` (or ``reset_cache()``) in tests that
    install or remove a pack at runtime.
    """
    by_slug: dict[str, PartnerPackManifest] = {}

    # Filesystem packs first so entry-point packs can override on collision.
    for manifest in _discover_filesystem_packs():
        by_slug[manifest.slug] = manifest
    for manifest in _discover_entrypoint_packs():
        by_slug[manifest.slug] = manifest

    manifests = sorted(by_slug.values(), key=lambda m: m.slug)
    if manifests:
        logger.info(
            "Discovered %d partner pack(s): %s",
            len(manifests),
            ", ".join(m.slug for m in manifests),
        )
    return manifests


def get_pack_by_slug(slug: str) -> PartnerPackManifest | None:
    """Return the discovered pack whose slug matches, or None."""
    for m in discover_packs():
        if m.slug == slug:
            return m
    return None


@lru_cache(maxsize=1)
def get_active_pack() -> PartnerPackManifest | None:
    """Pick the active pack.

    A pack becomes active either by being *applied* in-app (persisted via the
    /modules Partner Packs tab) or by the ``OE_PARTNER_PACK`` env var. Merely
    discovering packs (including the source-checkout packs under ``packs/``)
    never co-brands the app.

    Precedence:
      1. in-app applied pack (``partner_pack_state.json``)
      2. env ``OE_PARTNER_PACK=<slug>``
      3. None

    Cached for the process lifetime; ``reset_cache()`` is called by the apply
    service after an apply / un-apply so the change takes effect immediately.
    """
    # 1. In-app applied pack. Imported lazily to avoid any import-order issues.
    try:
        from app.core.partner_pack.state import get_applied_slug

        applied = get_applied_slug()
    except Exception:  # noqa: BLE001 — state file is best-effort
        applied = None
    if applied:
        m = get_pack_by_slug(applied)
        if m:
            logger.info("Active partner pack (in-app applied): %s", m.slug)
            return m
        logger.warning(
            "Applied partner pack '%s' is no longer installed; falling back.",
            applied,
        )

    # 2. env var.
    requested = os.environ.get("OE_PARTNER_PACK", "").strip()
    if requested:
        m = get_pack_by_slug(requested)
        if m:
            logger.info("Active partner pack (env-selected): %s", m.slug)
            return m
        logger.warning(
            "OE_PARTNER_PACK=%s requested but no such pack is installed.",
            requested,
        )
    return None


def get_active_pack_module_name() -> str | None:
    """Return the Python module name of the active pack, for resource loading.

    Resolves to e.g. ``openconstructionerp_batimatech_ca``. Used by
    ``router.py`` to stream the partner logo and onboarding script out of
    the installed pack package via ``importlib.resources``.

    Only pip-installed (entry-point) packs expose an importable module name;
    filesystem-only packs return ``None`` here (their resources are not on the
    import path). Since activation is env-driven and partners ship pip-installed
    packs in production, this matches the resource-streaming contract.
    """
    active = get_active_pack()
    if not active:
        return None
    try:
        eps = entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:
        eps = entry_points().get(ENTRY_POINT_GROUP, [])  # type: ignore[assignment]
    for ep in eps:
        if ep.name == active.slug:
            # ep.value is "module:attr" — return the module part
            return ep.value.split(":", 1)[0]
    return None


def _entrypoint_module_for_slug(slug: str) -> str | None:
    """Return the Python module name for a pip-installed pack by slug, or None."""
    try:
        eps = entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:
        eps = entry_points().get(ENTRY_POINT_GROUP, [])  # type: ignore[assignment]
    for ep in eps:
        if ep.name == slug:
            return ep.value.split(":", 1)[0]
    return None


def _fs_package_dir_for_slug(slug: str) -> Path | None:
    """Locate the on-disk package dir for a source-checkout pack by slug."""
    if not _PACKS_DIR.is_dir():
        return None

    def _pkg_dirs(pack_dir: Path) -> list[Path]:
        src_dir = pack_dir / "src"
        if not src_dir.is_dir():
            return []
        return [
            d
            for d in sorted(src_dir.glob("openconstructionerp_*"))
            if d.is_dir() and not d.name.endswith(".egg-info")
        ]

    # Fast path: the pack directory name matches the slug (repo convention).
    direct = _PACKS_DIR / slug
    for pkg_dir in _pkg_dirs(direct):
        if (pkg_dir / "manifest.py").is_file():
            return pkg_dir

    # Fallback: scan every pack and match the loaded manifest slug.
    for pack_dir in sorted(_PACKS_DIR.iterdir()):
        if not pack_dir.is_dir() or pack_dir == direct:
            continue
        for pkg_dir in _pkg_dirs(pack_dir):
            manifest_path = pkg_dir / "manifest.py"
            if not manifest_path.is_file():
                continue
            m = _load_manifest_from_file(manifest_path)
            if m and m.slug == slug:
                return pkg_dir
    return None


def read_pack_file(slug: str, relpath: str) -> bytes | None:
    """Read a file shipped inside a pack package, addressed by slug.

    Works for pip-installed (entry-point) packs via ``importlib.resources`` and
    for source-checkout packs under ``packs/<slug>/src/``. Path-traversal safe.
    Returns ``None`` when the pack or the file cannot be found. This is the
    by-slug counterpart to ``router._read_pack_resource`` (which only reads the
    active pack); the /modules grid uses it to show each pack's own logo.
    """
    rel = relpath.lstrip("/\\")
    if not rel or ".." in Path(rel.replace("\\", "/")).parts:
        return None

    # 1) pip-installed pack — read via importlib.resources.
    mod_name = _entrypoint_module_for_slug(slug)
    if mod_name:
        try:
            target = resources.files(mod_name).joinpath(rel)
            if target.is_file():
                return target.read_bytes()
        except (
            ModuleNotFoundError,
            FileNotFoundError,
            AttributeError,
            NotADirectoryError,
        ):
            pass

    # 2) source-checkout pack — read from the packs/ directory, sandboxed.
    pkg_dir = _fs_package_dir_for_slug(slug)
    if pkg_dir:
        base = pkg_dir.resolve()
        target = (base / rel).resolve()
        try:
            target.relative_to(base)
        except ValueError:
            return None
        if target.is_file():
            return target.read_bytes()
    return None


def reset_cache() -> None:
    """Reset the discovery caches. Used by tests."""
    discover_packs.cache_clear()
    get_active_pack.cache_clear()
