from fileformats.application import Json
from fileformats.core import validated_property
from fileformats.core.exceptions import FormatMismatchError
from fileformats.generic import BinaryFile, Directory, File, UnicodeFile
from fileformats.image import Cr2
from fileformats.medimage import MedicalImagingData


class Tom(BinaryFile, MedicalImagingData):
    """Canfield triangulated-object-mesh file: the reconstructed 3D surface
    (with texture) built from a set of stereo pod camera pairs."""

    ext = ".tom"


class Sfcm(BinaryFile, MedicalImagingData):
    """Canfield stereo feature/correlation map for a single pod camera, used
    to reconstruct the 3D mesh from its stereo image pair."""

    ext = ".sfcm"


class Cptr(BinaryFile, MedicalImagingData):
    """Canfield capture container recording the acquisition state/settings
    for a single 3D capture."""

    ext = ".cptr"


class TomSeedLog(UnicodeFile, MedicalImagingData):
    """Canfield log file recording the tom-seed process for a single 3D capture."""

    ext = ".tom-seed.log"


class TomTrackLog(UnicodeFile, MedicalImagingData):
    """Canfield log file recording the tom-track process for a single 3D capture."""

    ext = ".tom-track.log"


class CalibDir(Directory, MedicalImagingData):
    """Per-capture geometric calibration data for all of the stereo pod
    cameras."""

    contains_phi = "nested"

    @validated_property
    def sfcm_files(self) -> dict[str, Sfcm]:
        """Calibration stereo maps for each pod/side, keyed by e.g. 'a10A'."""
        dct = {p.stem: Sfcm(p) for p in self.fspath.glob("*.sfcm")}
        if not dct:
            raise FormatMismatchError(f"Did not find any *.sfcm files in {self.fspath}")
        return dct

    @validated_property
    def adjustframe_file(self) -> BinaryFile:
        return BinaryFile(self.fspath / "adjustframe.euc")

    @validated_property
    def info_file(self) -> File:
        return File(self.fspath / "info")

    @validated_property
    def tag_file(self) -> File:
        return File(self.fspath / "tag")


class TrackedDir(Directory, MedicalImagingData):
    """Output of tracking a captured region against a template mesh from an
    earlier visit, so it can be re-identified across time points."""

    @validated_property
    def template_file(self) -> Tom:
        matches = list(self.fspath.glob("track_template_*.tom"))
        if not matches:
            raise FormatMismatchError(
                f"Did not find a track_template_*.tom file in {self.fspath}"
            )
        return Tom(matches[0])

    @validated_property
    def seed_log_file(self) -> TomSeedLog:
        """Canfield log file recording the tom-seed process for a single 3D capture."""

        matches = list(self.fspath.glob("*.tom-seed.log"))
        if not matches:
            raise FormatMismatchError(
                f"Did not find a *.tom-seed.log file in {self.fspath}"
            )
        return TomSeedLog(matches[0])

    @validated_property
    def track_log_file(self) -> TomTrackLog:
        """Canfield log file recording the tom-track process for a single 3D capture."""

        matches = list(self.fspath.glob("*.tom-track.log"))
        if not matches:
            raise FormatMismatchError(
                f"Did not find a *.tom-track.log file in {self.fspath}"
            )
        return TomTrackLog(matches[0])

    @validated_property
    def tracking_log_file(self) -> UnicodeFile:
        return UnicodeFile(self.fspath / "tracking-log.txt")

    @validated_property
    def procstatus_file(self) -> UnicodeFile:
        return UnicodeFile(self.fspath / "lms" / "procstatus")

    @property
    def tracking_files(self) -> list[File]:
        """The opaque TRACKING_<capture-guid>_<template-guid> marker file(s)."""
        return [File(p) for p in self.fspath.glob("TRACKING_*")]


class WholeBodyAnalysisDir(Directory, MedicalImagingData):
    """Downstream lesion-detection/analysis pipeline output run over the
    whole-body capture, versioned by the analysis software release."""

    contains_phi = "nested"

    @validated_property
    def lesion_data_file(self) -> Json:
        matches = list(self.fspath.glob("lesion_data_*.json"))
        if not matches:
            raise FormatMismatchError(
                f"Did not find a lesion_data_*.json file in {self.fspath}"
            )
        return Json(matches[0])

    @validated_property
    def exitstatus_file(self) -> UnicodeFile:
        matches = list(self.fspath.glob("exitstatus_*.txt"))
        if not matches:
            raise FormatMismatchError(
                f"Did not find an exitstatus_*.txt file in {self.fspath}"
            )
        return UnicodeFile(matches[0])

    @validated_property
    def lesion_analysis_file(self) -> File:
        # FIXME: assumed to be a flat file by analogy with TrackedDir.tracking_files
        # (TRACKING_<guid>_<guid>), since the tree shows no contents nested under it
        # the way calib/ and Tracked_.../ do -- confirm against real data and update
        # to Directory (with a proper sub-format) if it turns out to have contents.
        matches = list(self.fspath.glob("LESION_ANALYSIS_*"))
        if not matches:
            raise FormatMismatchError(
                f"Did not find a LESION_ANALYSIS_* file in {self.fspath}"
            )
        return File(matches[0])


class WholeBodyCapture(Directory, MedicalImagingData):
    """Canfield Vectra whole-body 3D stereo-photogrammetry capture: the raw
    multi-pod camera images plus the reconstructed mesh and downstream lesion
    analysis for a single body scan."""

    @validated_property
    def mesh_file(self) -> Tom:
        """The reconstructed 3D mesh/texture for the capture, named after the
        capture timestamp (e.g. '20240730103101.tom')."""
        matches = list(self.fspath.glob("*.tom"))
        if not matches:
            raise FormatMismatchError(f"Did not find a *.tom file in {self.fspath}")
        return Tom(matches[0])

    @validated_property
    def capture_file(self) -> Cptr:
        return Cptr(self.fspath / "capture.cptr")

    @validated_property
    def config_file(self) -> UnicodeFile:
        return UnicodeFile(self.fspath / "a3d-config.ini")

    @validated_property
    def context_file(self) -> File:
        return File(self.fspath / "context")

    @validated_property
    def dcontext_file(self) -> File:
        return File(self.fspath / "Dcontext")

    @validated_property
    def camera_info_file(self) -> File:
        return File(self.fspath / "camerainfo")

    @validated_property
    def flash_status_file(self) -> File:
        return File(self.fspath / "flashstatus")

    @validated_property
    def preview_file(self) -> File:
        return File(self.fspath / "1C.png")

    @validated_property
    def calib_dir(self) -> CalibDir:
        return CalibDir(self.fspath / "calib")

    @validated_property
    def analysis_dir(self) -> WholeBodyAnalysisDir:
        return WholeBodyAnalysisDir(self.fspath / "analysis")

    @property
    def sglue_log_file(self) -> UnicodeFile | None:
        path = self.fspath / "sglue-log.txt"
        return UnicodeFile(path) if path.exists() else None

    @validated_property
    def tracked_dirs(self) -> dict[str, TrackedDir]:
        """Tracking sub-directories, keyed by capture GUID."""
        dct = {
            p.name.split("_", 1)[1]: TrackedDir(p)
            for p in self.fspath.glob("Tracked_*")
            if p.is_dir()
        }
        return dct

    @property
    def pod_images(self) -> dict[str, Cr2]:
        """Raw per-pod camera images, keyed by e.g. 'a10A'/'f10B'."""
        return {p.stem: Cr2(p) for p in self.fspath.glob("[af]*[AB].CR2")}

    @property
    def pod_stereo_maps(self) -> dict[str, Sfcm]:
        """Per-capture stereo feature maps, keyed the same way as pod_images."""
        return {p.stem: Sfcm(p) for p in self.fspath.glob("[af]*[AB].sfcm")}

    @property
    def log_files(self) -> list[UnicodeFile]:
        """Processing-pipeline logs from capture, calibration and 3D
        reconstruction (per-pod stereo logs, calibration tweaks, mesh
        gluing/texturing, etc.)."""
        return [UnicodeFile(p) for p in self.fspath.glob("*log*.txt")]
