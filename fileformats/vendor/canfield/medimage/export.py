from fileformats.application import Pdf
from fileformats.core import validated_property
from fileformats.core.exceptions import FormatMismatchError
from fileformats.generic import Directory
from fileformats.medimage import MedicalImagingData

from .lesion import LesionAnalysisDir, T2k
from .whole_body import WholeBodyCapture


class VectraExport(Directory, MedicalImagingData):
    """Canfield data export directory: a session/patient-level export
    containing whole-body 3D captures, hand-held single-lesion captures and
    their Vectra/Dexi lesion analyses, at least one of each. The three aren't
    necessarily 1-1 (e.g. not every lesion capture has been analysed), so each
    sub-type is discovered independently rather than cross-referenced."""

    @validated_property
    def has_content(self) -> bool:
        """Checks the export contains at least one each of T2k file, whole-body
        capture and lesion analysis"""
        missing = [
            name
            for name, found in (
                ("T2k files", self.t2k_files),
                ("WholeBodyCapture sub-directories", self.whole_body_capture_dirs),
                ("LesionAnalysisDir sub-directories", self.lesion_analysis_dirs),
            )
            if not found
        ]
        if missing:
            raise FormatMismatchError(
                f"Did not find any {' or '.join(missing)} within the export "
                f"directory {self.fspath}, which requires at least one of each"
            )
        return True

    @property
    def t2k_files(self) -> dict[str, T2k]:
        """Hand-held single-lesion captures, keyed by capture timestamp."""
        return {p.stem: T2k(p) for p in self.fspath.glob("*.t2k")}

    @validated_property
    def whole_body_capture_dirs(self) -> dict[str, WholeBodyCapture]:
        """Whole-body 3D stereo-photogrammetry captures, keyed by capture
        timestamp."""
        return {
            p.name: WholeBodyCapture(p)
            for p in self.fspath.iterdir()
            if p.is_dir() and WholeBodyCapture.matches(p)
        }

    @validated_property
    def lesion_analysis_dirs(self) -> dict[str, LesionAnalysisDir]:
        """Vectra/Dexi lesion analyses, keyed by capture timestamp."""
        return {
            p.name: LesionAnalysisDir(p)
            for p in self.fspath.iterdir()
            if p.is_dir() and LesionAnalysisDir.matches(p)
        }

    @property
    def dermx_reports(self) -> list[Pdf]:
        """DermX PDF reports"""
        return [Pdf(p) for p in self.fspath.glob("DermX Report*.pdf")]
