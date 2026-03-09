import os
import logging
import tempfile
import shutil
from typing import List

from app.processing.structuring_lib.styler import process_docx
from app.core.config import get_settings
from app.services.ai_structuring_client import AIStructuringClient, AIStructuringSettings

# Configure specialised logger
logger = logging.getLogger("app.processing.structuring")

class StructuringEngine:
    """
    Wrapper engine for Book Styler integration.

    Best-practice: keep local structuring as the default.
    If AI_STRUCTURING_BASE_URL is set in .env, this engine will offload the work to the
    external AI-Structuring service (submit -> poll -> download) and then write the
    processed DOCX back into the CMS storage.
    """

    def process_document(self, file_path: str, mode: str = "style") -> List[str]:
        """
        Run structuring process on a DOCX file.

        Args:
            file_path: Absolute path to the input .docx file
            mode: "style" (Apply Styles & Validate) or "tag" (Add Tags Only)

        Returns:
            List of generated file paths (usually just one processed file)
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Input file not found: {file_path}")

        # Standard naming convention: original_name_Processed.docx
        dir_name = os.path.dirname(file_path)
        base_name = os.path.basename(file_path)
        name_only = os.path.splitext(base_name)[0]
        output_filename = f"{name_only}_Processed.docx"
        output_path = os.path.join(dir_name, output_filename)

        settings = get_settings()

        # External AI structuring (disabled by default)
        if getattr(settings, "AI_STRUCTURING_BASE_URL", ""):
            logger.info(f"Starting AI structuring offload (mode={mode}) for: {base_name}")
            client = AIStructuringClient(
                AIStructuringSettings(
                    base_url=settings.AI_STRUCTURING_BASE_URL,
                    api_key=getattr(settings, "AI_STRUCTURING_API_KEY", ""),
                    document_type=getattr(settings, "AI_STRUCTURING_DOCUMENT_TYPE", "Academic Document"),
                    use_markers=getattr(settings, "AI_STRUCTURING_USE_MARKERS", False),
                    poll_interval_seconds=getattr(settings, "AI_STRUCTURING_POLL_INTERVAL_SECONDS", 2),
                    max_wait_seconds=getattr(settings, "AI_STRUCTURING_MAX_WAIT_SECONDS", 900),
                    request_timeout_seconds=getattr(settings, "AI_STRUCTURING_REQUEST_TIMEOUT_SECONDS", 30),
                )
            )

            # Use a predictable batch name for traceability
            batch_name = f"cms_structuring_{name_only}"

            tmp_dir = tempfile.mkdtemp(prefix="cms_ai_structuring_")
            try:
                batch_id = client.submit_batch(file_path=file_path, batch_name=batch_name)
                status_payload = client.wait_for_completion(batch_id)

                # Download zip and extract processed docx
                zip_path = os.path.join(tmp_dir, f"{batch_id}.zip")
                client.download_zip(batch_id, zip_path)

                extracted_docx = client.extract_first_processed_docx(zip_path, tmp_dir)

                # The extracted path might include subfolders; move/copy into output_path
                shutil.copyfile(extracted_docx, output_path)

                logger.info(f"AI structuring completed. Output written to: {output_path}")
                return [output_path]
            except Exception as e:
                logger.error(f"AI structuring failed; falling back to local structuring. Error: {e}", exc_info=True)
                # Fall back to local structuring below
            finally:
                try:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                except Exception:
                    pass

        # Local structuring (current default)
        logger.info(f"Starting local structuring (mode={mode}) for: {base_name}")
        result = process_docx(
            input_path=file_path,
            output_path=output_path,
            mode=mode
        )

        if not result.get("success", False):
            error_msg = "; ".join(result.get("errors", ["Unknown structuring error"]))
            logger.error(f"Structuring failed: {error_msg}")
            raise Exception(f"Structuring failed: {error_msg}")

        logger.info(f"Structuring successful. Processed {result.get('paragraphs_processed')} paragraphs.")
        return [output_path]
