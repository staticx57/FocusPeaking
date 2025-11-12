"""
Data export utilities for FLIR Boson Focus Peaking.

Provides CSV export, data logging, and statistics export functionality.
"""

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

from config import CSV_EXPORT_DELIMITER, CSV_EXPORT_DECIMAL

logger = logging.getLogger(__name__)


class FocusDataExporter:
    """
    Handles export of focus data to various formats.
    """

    def __init__(self):
        """Initialize the data exporter."""
        self.session_start = datetime.now()

    def export_to_csv(
        self,
        filename: str,
        focus_history: List[float],
        roi_data: Optional[List[Dict]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Export focus data to CSV file.

        Args:
            filename: Output CSV filename
            focus_history: List of focus scores over time
            roi_data: Optional list of ROI configurations
            metadata: Optional metadata to include

        Returns:
            True if export successful, False otherwise
        """
        try:
            filepath = Path(filename)

            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(
                    csvfile,
                    delimiter=CSV_EXPORT_DELIMITER
                )

                # Write metadata header
                if metadata:
                    writer.writerow(['# Metadata'])
                    for key, value in metadata.items():
                        writer.writerow([f'# {key}', str(value)])
                    writer.writerow([])

                # Write session info
                writer.writerow(['# Session Information'])
                writer.writerow(['# Session Start', self.session_start.isoformat()])
                writer.writerow(['# Export Time', datetime.now().isoformat()])
                writer.writerow(['# Total Samples', len(focus_history)])
                writer.writerow([])

                # Write ROI configuration if provided
                if roi_data:
                    writer.writerow(['# ROI Configuration'])
                    writer.writerow(['ROI_ID', 'X1', 'Y1', 'X2', 'Y2', 'Weight'])
                    for roi in roi_data:
                        rect = roi.get('rect', [0, 0, 0, 0])
                        writer.writerow([
                            roi.get('id', 0),
                            rect[0], rect[1], rect[2], rect[3],
                            roi.get('weight', 1.0)
                        ])
                    writer.writerow([])

                # Write focus data
                writer.writerow(['# Focus Data'])
                writer.writerow(['Sample', 'Timestamp_Offset_Sec', 'Focus_Score'])

                for idx, score in enumerate(focus_history):
                    timestamp_offset = idx * 0.05  # Assuming 20 FPS
                    writer.writerow([
                        idx,
                        f"{timestamp_offset:.2f}",
                        f"{score:.2f}"
                    ])

            logger.info(f"Successfully exported focus data to {filepath}")
            return True

        except Exception as e:
            logger.error(f"Failed to export to CSV: {e}")
            return False

    def export_statistics_to_csv(
        self,
        filename: str,
        stats: Dict[str, float]
    ) -> bool:
        """
        Export focus statistics to CSV.

        Args:
            filename: Output CSV filename
            stats: Dictionary of statistics

        Returns:
            True if successful
        """
        try:
            filepath = Path(filename)

            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile, delimiter=CSV_EXPORT_DELIMITER)

                writer.writerow(['# Focus Statistics'])
                writer.writerow(['Export Time', datetime.now().isoformat()])
                writer.writerow([])

                writer.writerow(['Metric', 'Value'])
                for metric, value in stats.items():
                    writer.writerow([metric, f"{value:.2f}"])

            logger.info(f"Statistics exported to {filepath}")
            return True

        except Exception as e:
            logger.error(f"Failed to export statistics: {e}")
            return False

    def export_roi_config(
        self,
        filename: str,
        roi_data: List[Dict]
    ) -> bool:
        """
        Export ROI configuration to JSON.

        Args:
            filename: Output JSON filename
            roi_data: List of ROI dictionaries

        Returns:
            True if successful
        """
        try:
            filepath = Path(filename)

            export_data = {
                'export_time': datetime.now().isoformat(),
                'roi_count': len(roi_data),
                'rois': roi_data
            }

            with open(filepath, 'w', encoding='utf-8') as jsonfile:
                json.dump(export_data, jsonfile, indent=2)

            logger.info(f"ROI config exported to {filepath}")
            return True

        except Exception as e:
            logger.error(f"Failed to export ROI config: {e}")
            return False

    def create_session_report(
        self,
        filename: str,
        focus_history: List[float],
        roi_data: List[Dict],
        stats: Dict[str, float],
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Create comprehensive session report in text format.

        Args:
            filename: Output text filename
            focus_history: Focus score history
            roi_data: ROI configuration
            stats: Statistics dictionary
            metadata: Optional metadata

        Returns:
            True if successful
        """
        try:
            filepath = Path(filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                # Header
                f.write("=" * 70 + "\n")
                f.write("FLIR Boson Focus Peaking - Session Report\n")
                f.write("=" * 70 + "\n\n")

                # Session info
                f.write("Session Information:\n")
                f.write("-" * 70 + "\n")
                f.write(f"Session Start: {self.session_start}\n")
                f.write(f"Report Generated: {datetime.now()}\n")
                f.write(f"Duration: {(datetime.now() - self.session_start)}\n")
                f.write(f"Total Samples: {len(focus_history)}\n\n")

                # Metadata
                if metadata:
                    f.write("Metadata:\n")
                    f.write("-" * 70 + "\n")
                    for key, value in metadata.items():
                        f.write(f"{key}: {value}\n")
                    f.write("\n")

                # Statistics
                f.write("Focus Statistics:\n")
                f.write("-" * 70 + "\n")
                for metric, value in stats.items():
                    f.write(f"{metric:20s}: {value:10.2f}\n")
                f.write("\n")

                # ROI Configuration
                f.write("ROI Configuration:\n")
                f.write("-" * 70 + "\n")
                f.write(f"Total ROIs: {len(roi_data)}\n\n")
                for roi in roi_data:
                    f.write(f"  ROI {roi.get('id')}:\n")
                    rect = roi.get('rect', [0, 0, 0, 0])
                    f.write(f"    Position: ({rect[0]}, {rect[1]}) to ({rect[2]}, {rect[3]})\n")
                    f.write(f"    Weight: {roi.get('weight', 1.0):.2f}\n")
                    f.write(f"    Score: {roi.get('score', 0.0):.2f}\n\n")

                # Summary
                f.write("\n" + "=" * 70 + "\n")
                f.write("End of Report\n")
                f.write("=" * 70 + "\n")

            logger.info(f"Session report created: {filepath}")
            return True

        except Exception as e:
            logger.error(f"Failed to create session report: {e}")
            return False


def generate_default_export_filename(
    prefix: str = "focus_data",
    extension: str = "csv"
) -> str:
    """
    Generate a default filename with timestamp.

    Args:
        prefix: Filename prefix
        extension: File extension (without dot)

    Returns:
        Generated filename
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}.{extension}"


def quick_export_csv(
    focus_history: List[float],
    roi_data: Optional[List[Dict]] = None,
    output_dir: str = "."
) -> Optional[str]:
    """
    Quick export with auto-generated filename.

    Args:
        focus_history: Focus score history
        roi_data: Optional ROI data
        output_dir: Output directory

    Returns:
        Path to created file, or None if failed
    """
    try:
        filename = generate_default_export_filename()
        filepath = Path(output_dir) / filename

        exporter = FocusDataExporter()
        success = exporter.export_to_csv(str(filepath), focus_history, roi_data)

        if success:
            return str(filepath)
        return None

    except Exception as e:
        logger.error(f"Quick export failed: {e}")
        return None
