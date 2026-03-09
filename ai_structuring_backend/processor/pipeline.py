"""
Document Processing Pipeline
Simplified interface for the queue service.
"""

import os
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Callable, Optional

from .blocks import extract_blocks
from .classifier import classify_blocks_with_prompt
from .reconstruction import DocumentReconstructor
from .confidence import ConfidenceFilter
from .validator import validate_and_repair
from .style_trace import emit_style_tag_trace
from .marker_rules import apply_marker_overrides
from .box_normalizer import normalize_box_styles
from .list_normalizer import normalize_list_runs
from .table_note_rules import apply_table_note_overrides
from .question_ref_normalizer import normalize_reference_numbering as normalize_question_refs
from .ref_numbering import normalize_reference_numbering
from .table_title_rules import enforce_table_title_rules
from .list_hierarchy import enforce_list_hierarchy_from_word_xml
from .marker_lock import lock_marker_blocks, relock_marker_classifications
from .zone_style_restriction import (
    restrict_allowed_styles_per_zone,
    enforce_zone_style_restrictions,
)
from .reference_label_normalizer import normalize_reference_labels
from .table_title_normalizer import normalize_table_titles
from .reference_numbering_normalizer import normalize_reference_numbering as normalize_reference_format
from .list_preservation import enforce_list_hierarchy_from_word_xml as preserve_list_hierarchy
from .table_title_enforcement import enforce_table_title_house_rules
from .structure_guard import enforce_style_only_mutation
from .style_enforcement import enforce_style_compliance
from .table_cell_position_normalizer import normalize_table_cell_positions
from .integrity import run_integrity_trigger
from .structural_invariants import (
    BlockTransformPolicy,
    STYLE_TAG_ONLY_POLICY,
    snapshot_blocks_for_contract,
    validate_block_transform_contract,
)
from app.services.allowed_styles import load_allowed_styles
from app.services.prompt_router import route_prompt
from app.services.quality_score import score_document
from app.services.review_bundle import create_review_bundle

logger = logging.getLogger(__name__)

_PIPELINE_BLOCK_STAGE_POLICY = BlockTransformPolicy(
    allow_length_change=False,
    allow_reorder=False,
    allow_id_rewrite=False,
    allow_text_changes=True,
    stage_type="pipeline_block_stage",
)


def _run_block_transform_stage(stage_name: str, fn, blocks: list[dict], *args, policy=None, **kwargs) -> list[dict]:
    """Run a block transform and fail fast if it mutates count/order/IDs unexpectedly."""
    before = snapshot_blocks_for_contract(blocks)
    result = fn(blocks, *args, **kwargs)
    out_blocks = list(result) if result is not None else list(blocks)
    try:
        validate_block_transform_contract(
            before,
            out_blocks,
            stage=stage_name,
            policy=policy or _PIPELINE_BLOCK_STAGE_POLICY,
        )
    except AssertionError as exc:
        logger.error("BLOCK_STAGE_INVARIANT_FAIL stage=%s error=%s", stage_name, exc)
        raise RuntimeError(str(exc)) from exc
    return out_blocks


def process_document(
    input_path: str,
    output_folder: str,
    document_type: str = "Academic Document",
    use_markers: bool = False,
    classifier_override: Optional[Callable[[list[dict], list[dict]], list[dict]]] = None,
    apply_repair: bool = True,
    job_id: str | None = None,
) -> dict:
    """
    Process a single document through the full pipeline.
    
    Args:
        input_path: Path to input DOCX file
        output_folder: Base output folder (with processed/review/json subfolders)
        document_type: Type of document for classification
        use_markers: Whether to use XML markers (True) or Word styles (False)
        
    Returns:
        Dictionary with results and file paths
    """
    input_path = Path(input_path)
    output_folder = Path(output_folder)
    
    logger.info(f"Processing: {input_path.name}")
    
    # Stage 1: Ingestion
    logger.info("Stage 1: Document Ingestion (Blocks + Structural Features)")
    blocks, paragraphs, stats = extract_blocks(input_path)
    
    # Stage 1b: Deterministic pre-classification locks (before LLM)
    blocks = _run_block_transform_stage("marker_lock", lock_marker_blocks, blocks, policy=STYLE_TAG_ONLY_POLICY)
    blocks = _run_block_transform_stage("table_title_rules", enforce_table_title_rules, blocks)
    blocks = _run_block_transform_stage("reference_numbering_pre", normalize_reference_numbering, blocks)
    blocks = _run_block_transform_stage("list_hierarchy_lock", enforce_list_hierarchy_from_word_xml, blocks)
    blocks = _run_block_transform_stage("zone_style_restriction", restrict_allowed_styles_per_zone, blocks)

    # Stage 2: Classification (Option 2 retry ladder)
    logger.info("Stage 2: AI Classification")
    token_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    retry_count = 0
    quality_score = None
    quality_action = None
    quality_metrics = {}

    allowed_styles = load_allowed_styles()

    if classifier_override:
        classifications = classifier_override(blocks, paragraphs)
        if apply_repair:
            classifications = validate_and_repair(
                classifications,
                blocks,
                allowed_styles=allowed_styles,
                preserve_lists=use_markers,
                preserve_marker_pmi=use_markers,
            )
        classifications = apply_marker_overrides(blocks, classifications)
        classifications = normalize_box_styles(blocks, classifications, allowed_styles)
        classifications = normalize_list_runs(blocks, classifications, allowed_styles)
        classifications = apply_table_note_overrides(blocks, classifications, allowed_styles)
        classifications = normalize_question_refs(blocks, classifications, allowed_styles)

        # Stage 3.5: Post-classification text/placement normalization
        blocks = _run_block_transform_stage("reference_label_normalizer", normalize_reference_labels, blocks)
        blocks = _run_block_transform_stage(
            "table_title_normalizer",
            normalize_table_titles,
            blocks,
            policy=STYLE_TAG_ONLY_POLICY,
        )
        blocks = _run_block_transform_stage("reference_numbering_format_normalizer", normalize_reference_format, blocks)

        # Sync block tags back to classifications after normalizers modify them
        block_tags = {b["id"]: b.get("tag") for b in blocks if "tag" in b}
        for clf in classifications:
            if clf["id"] in block_tags and block_tags[clf["id"]]:
                clf["tag"] = block_tags[clf["id"]]

        # Enforce list hierarchy from Word XML (final authority on list structure)
        classifications = preserve_list_hierarchy(blocks, classifications)

        # Re-lock marker blocks (final authority on marker-only paragraphs)
        classifications = relock_marker_classifications(blocks, classifications)

        # Normalize table-cell list positions (TBL-FIRST / TBL-MID / TBL-LAST)
        classifications = normalize_table_cell_positions(classifications, blocks)

        # Score once for override path
        scored_blocks = []
        clf_by_id = {c["id"]: c for c in classifications}
        for b in blocks:
            c = clf_by_id.get(b["id"], {})
            scored_blocks.append(
                {
                    **b,
                    "tag": c.get("tag", "TXT"),
                    "confidence": c.get("confidence", 0),
                    "repaired": c.get("repaired", False),
                    "repair_reason": c.get("repair_reason"),
                }
            )

        # Enforce zone style restrictions (final safety net before quality scoring)
        scored_blocks = enforce_zone_style_restrictions(scored_blocks, allowed_styles)

        quality_score, quality_metrics, quality_action = score_document(scored_blocks, allowed_styles)
    else:
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set")

        primary_model = os.getenv("GEMINI_MODEL_PRIMARY", "gemini-2.5-pro")
        strong_model = os.getenv("GEMINI_MODEL_STRONG", "gemini-2.5-pro")

        classifications = []
        for attempt in range(1, 4):
            if attempt == 1:
                prompt_name = "default"
                prompt_text = None
                model_name = primary_model
            else:
                prompt_name, prompt_text = route_prompt(blocks)
                model_name = primary_model if attempt == 2 else strong_model

            logger.info(f"Attempt {attempt}: model={model_name}, prompt={prompt_name}")
            classifications, token_usage = classify_blocks_with_prompt(
                blocks=blocks,
                document_name=input_path.name,
                api_key=api_key,
                document_type=document_type,
                model_name=model_name,
                system_prompt_override=prompt_text,
            )

            if apply_repair:
                logger.info("Stage 3: Validation + Deterministic Repair")
                classifications = validate_and_repair(
                    classifications,
                    blocks,
                    allowed_styles=allowed_styles,
                    preserve_lists=use_markers,
                    preserve_marker_pmi=use_markers,
                )
            classifications = apply_marker_overrides(blocks, classifications)
            classifications = normalize_box_styles(blocks, classifications, allowed_styles)
            classifications = normalize_list_runs(blocks, classifications, allowed_styles)
            classifications = apply_table_note_overrides(blocks, classifications, allowed_styles)
            classifications = normalize_question_refs(blocks, classifications, allowed_styles)

            # Stage 3.5: Post-classification text/placement normalization
            blocks = _run_block_transform_stage("reference_label_normalizer", normalize_reference_labels, blocks)
            blocks = _run_block_transform_stage(
                "table_title_normalizer",
                normalize_table_titles,
                blocks,
                policy=STYLE_TAG_ONLY_POLICY,
            )
            blocks = _run_block_transform_stage("reference_numbering_format_normalizer", normalize_reference_format, blocks)

            # Sync block tags back to classifications after normalizers modify them
            block_tags = {b["id"]: b.get("tag") for b in blocks if "tag" in b}
            for clf in classifications:
                if clf["id"] in block_tags and block_tags[clf["id"]]:
                    clf["tag"] = block_tags[clf["id"]]

            # Enforce list hierarchy from Word XML (final authority on list structure)
            classifications = preserve_list_hierarchy(blocks, classifications)

            # Re-lock marker blocks (final authority on marker-only paragraphs)
            classifications = relock_marker_classifications(blocks, classifications)

            # Normalize table-cell list positions (TBL-FIRST / TBL-MID / TBL-LAST)
            classifications = normalize_table_cell_positions(classifications, blocks)

            # Score document quality
            scored_blocks = []
            clf_by_id = {c["id"]: c for c in classifications}
            for b in blocks:
                c = clf_by_id.get(b["id"], {})
                scored_blocks.append(
                    {
                        **b,
                        "tag": c.get("tag", "TXT"),
                        "confidence": c.get("confidence", 0),
                        "repaired": c.get("repaired", False),
                        "repair_reason": c.get("repair_reason"),
                    }
                )

            # Enforce zone style restrictions (final safety net before quality scoring)
            scored_blocks = enforce_zone_style_restrictions(scored_blocks, allowed_styles)

            quality_score, quality_metrics, quality_action = score_document(scored_blocks, allowed_styles)

            if quality_action == "PASS":
                break
            if quality_action == "RETRY" and attempt < 3:
                retry_count += 1
                continue
            break

    # Diagnostics: emit STYLE_TAG_TRACE when STYLE_TRACE=1
    emit_style_tag_trace(input_path.name, blocks, classifications)

    # Stage 4: Confidence Filtering
    logger.info("Stage 4: Confidence Filtering")
    filter_service = ConfidenceFilter(threshold=85)
    filtered = filter_service.filter(classifications, paragraphs)

    # Stage 4.5: Final Style Enforcement (safety gate)
    logger.info("Stage 4.5: Final style enforcement")
    # Extract classifications from FilteredResults (auto_apply + needs_review)
    filtered_clfs = [r.to_dict() for r in filtered.auto_apply + filtered.needs_review]
    classifications = enforce_style_compliance(
        classifications=filtered_clfs,
        blocks=blocks,
        allowed_styles=allowed_styles,
    )

    # Preserve lightweight zone metadata for reconstruction-time review highlighting.
    block_meta_by_id = {b["id"]: (b.get("metadata") or {}) for b in blocks}
    for clf in classifications:
        meta = block_meta_by_id.get(clf.get("id"), {})
        if not meta:
            continue
        clf["context_zone"] = meta.get("context_zone")
        clf["is_reference_zone"] = bool(meta.get("is_reference_zone"))

    # Stage 5: Reconstruction
    logger.info("Stage 5: Document Reconstruction")
    
    # Generate output filenames
    base_name = input_path.stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    output_name = f"{base_name}_processed.docx"
    review_name = f"{base_name}_processed_review.docx"
    json_name = f"{base_name}_processed_results.json"
    
    # Create reconstructor with temp directory, then move files
    temp_dir = output_folder / "temp"
    temp_dir.mkdir(exist_ok=True)
    
    reconstructor = DocumentReconstructor(output_dir=str(temp_dir))
    
    if use_markers:
        tagged_path = reconstructor.apply_tags_with_markers(
            source_path=input_path,
            classifications=classifications,
            output_name=output_name
        )
    else:
        tagged_path = reconstructor.apply_styles(
            source_path=input_path,
            classifications=classifications,
            output_name=output_name
        )

    # Diagnostic: log tagged_path immediately after reconstruction
    if tagged_path:
        tagged_exists = Path(tagged_path).exists()
        logger.info(
            f"Reconstructor returned tagged_path={tagged_path} "
            f"(exists={tagged_exists})"
        )
        if not tagged_exists:
            logger.error(
                f"OUTPUT_DIAGNOSTIC: tagged_path does not exist on disk. "
                f"base_name={base_name}, temp_dir={temp_dir}, "
                f"expected_output_name={output_name}"
            )
    else:
        logger.error(
            f"OUTPUT_DIAGNOSTIC: Reconstructor returned tagged_path=None. "
            f"base_name={base_name}, temp_dir={temp_dir}, "
            f"expected_output_name={output_name}"
        )

    # Generate review report
    review_path = reconstructor.generate_review_report(
        document_name=input_path.name,
        filtered_results=filtered.to_dict(),
        output_name=review_name
    )
    
    # Generate JSON results
    json_path = reconstructor.generate_json_output(
        document_name=input_path.name,
        classifications=classifications,
        filtered_results=filtered.to_dict(),
        output_name=json_name
    )
    
    # Generate HTML report
    html_name = f"{base_name}_processed_report.html"
    html_path = reconstructor.generate_html_report(
        document_name=input_path.name,
        classifications=classifications,
        filtered_results=filtered.to_dict(),
        output_name=html_name
    )
    
    # Move files to proper subfolders
    final_paths = {}

    if tagged_path and Path(tagged_path).exists():
        dest = output_folder / "processed" / output_name
        shutil.move(str(tagged_path), str(dest))
        final_paths['output_path'] = str(dest)

    # Stage 5.25: Table Title House Rules (post-reconstruction enforcement)
    if 'output_path' in final_paths:
        logger.info("Stage 5.25: Table Title House Rules Enforcement")
        try:
            tt_metrics = enforce_table_title_house_rules(final_paths['output_path'])
        except Exception as exc:
            logger.warning("Table title enforcement failed (non-fatal): %s", exc)

    # Stage 5.5: Structure Guard (AUTOMATIC HARD GATE)
    # Enforces style-only mutations - FAIL FAST on structural changes
    structure_result = None
    if 'output_path' in final_paths:
        logger.info("Stage 5.5: Structure Guard (Style-Only Mutation Check)")
        try:
            structure_result = enforce_style_only_mutation(
                input_path=str(input_path),
                output_path=final_paths['output_path']
            )
            # If we get here, structure guard passed
            logger.info(
                f"STRUCTURE_GUARD_PASS: Only style changes detected. "
                f"Paragraph count: {structure_result['paragraph_count_match']}, "
                f"Hash match: {structure_result['structural_hash_match']}"
            )
        except RuntimeError as e:
            # Structure guard failed - structural mutation detected
            logger.error(f"STRUCTURE_GUARD_FAIL: {str(e)[:500]}")
            # Return failure result immediately - do NOT proceed to integrity or quality scoring
            return {
                'status': 'FAILED',
                'error': 'STRUCTURE_GUARD_FAIL',
                'stage': 'structure_guard',
                'diagnostics': structure_result if structure_result else {'status': 'FAIL', 'error': str(e)[:1000]},
                'structure_guard': structure_result if structure_result else {'status': 'FAIL', 'error': str(e)[:1000]},
                'message': f"Structure guard failed: processor mutated document structure.",
                'total_paragraphs': stats.get('total_paragraphs', 0),
                'input_tokens': token_usage.get('input_tokens', 0),
                'output_tokens': token_usage.get('output_tokens', 0),
                'total_tokens': token_usage.get('total_tokens', 0),
            }

    # Stage 6: Integrity Verification (AUTOMATIC HARD GATE)
    # Verifies both content and structural integrity
    integrity_result = None
    if 'output_path' in final_paths:
        logger.info("Stage 6: Integrity Verification (Content + Structural)")
        try:
            integrity_result = run_integrity_trigger(
                input_path=str(input_path),
                output_path=final_paths['output_path']
            )
            # If we get here, integrity passed
            logger.info(
                f"INTEGRITY_PASS: Content and structure preserved. "
                f"Input: {integrity_result['content_integrity']['input_paragraphs']} paras, "
                f"{integrity_result['content_integrity']['input_tables']} tables"
            )
        except RuntimeError as e:
            # Integrity check failed - detailed error already logged by integrity module
            logger.error(f"INTEGRITY_TRIGGER_FAIL: {str(e)[:500]}")
            # Return failure result immediately - do NOT proceed to quality scoring
            return {
                'status': 'FAILED',
                'error': 'INTEGRITY_TRIGGER_FAIL',
                'stage': 'integrity_check',
                'diagnostics': integrity_result if integrity_result else {'status': 'ERROR', 'error': str(e)[:1000]},
                'integrity_check': integrity_result if integrity_result else {'status': 'ERROR', 'error': str(e)[:1000]},
                'message': f"Integrity verification failed. See logs for details.",
                'total_paragraphs': stats.get('total_paragraphs', 0),
                'input_tokens': token_usage.get('input_tokens', 0),
                'output_tokens': token_usage.get('output_tokens', 0),
                'total_tokens': token_usage.get('total_tokens', 0),
            }

    if review_path and Path(review_path).exists():
        dest = output_folder / "review" / review_name
        shutil.move(str(review_path), str(dest))
        final_paths['review_path'] = str(dest)
    
    if json_path and Path(json_path).exists():
        dest = output_folder / "json" / json_name
        shutil.move(str(json_path), str(dest))
        final_paths['json_path'] = str(dest)
    
    if html_path and Path(html_path).exists():
        # Create html folder if needed
        html_folder = output_folder / "html"
        html_folder.mkdir(exist_ok=True)
        dest = html_folder / html_name
        shutil.move(str(html_path), str(dest))
        final_paths['html_path'] = str(dest)
    
    # Diagnostic: if output_path was never set, list temp_dir contents before cleanup
    if 'output_path' not in final_paths and temp_dir.exists():
        try:
            temp_files = [f.name for f in temp_dir.iterdir()]
            logger.error(
                f"OUTPUT_DIAGNOSTIC: output_path missing from final_paths. "
                f"Files in temp_dir ({temp_dir}): {temp_files}"
            )
        except OSError as e:
            logger.error(f"OUTPUT_DIAGNOSTIC: Could not list temp_dir: {e}")

    # Cleanup temp directory
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    
    review_bundle_path = None
    if quality_action == "REVIEW":
        # build decisions payload
        clf_by_id = {c["id"]: c for c in classifications}
        decisions = []
        for b in blocks:
            c = clf_by_id.get(b["id"], {})
            decisions.append(
                {
                    "id": b["id"],
                    "text": b.get("text", ""),
                    "tag": c.get("tag"),
                    "confidence": c.get("confidence"),
                    "repaired": c.get("repaired", False),
                    "repair_reason": c.get("repair_reason"),
                }
            )
        review_bundle_path = create_review_bundle(
            job_id or input_path.stem,
            str(input_path),
            final_paths.get("output_path", ""),
            decisions,
            {
                "score": quality_score,
                "action": quality_action,
                "metrics": quality_metrics,
                "retry_count": retry_count,
            },
        )

    # Build result
    result = {
        'status': 'SUCCESS',
        **final_paths,
        'total_paragraphs': stats.get('total_paragraphs', 0),
        'auto_applied': filtered.auto_applied_count if hasattr(filtered, 'auto_applied_count') else 0,
        'needs_review': filtered.needs_review_count if hasattr(filtered, 'needs_review_count') else 0,
        'input_tokens': token_usage.get('input_tokens', 0),
        'output_tokens': token_usage.get('output_tokens', 0),
        'total_tokens': token_usage.get('total_tokens', 0),
        'quality_score': quality_score,
        'quality_action': quality_action,
        'retry_count': retry_count,
        'review_bundle_path': review_bundle_path,
        'structure_guard': structure_result,
        'integrity_check': integrity_result,
    }
    
    logger.info(f"Completed: {input_path.name}")
    logger.info(f"  Total paragraphs: {result['total_paragraphs']}")
    logger.info(f"  Tokens used: {result['total_tokens']:,}")
    
    return result
