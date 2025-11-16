"""
COS upload tasks for audio files.

Prefect tasks for uploading audio files to Tencent Cloud COS.
"""

import os
from pathlib import Path
from typing import Any, Dict, List

from qcloud_cos import CosConfig, CosS3Client
from qcloud_cos.cos_exception import CosServiceError, CosClientError

from prefect import task, get_run_logger
from prefect.cache_policies import NONE

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class COSUploadError(Exception):
    """Custom exception for COS upload errors"""
    pass


@task(name="Load COS Configuration", retries=1)
def load_cos_config() -> Dict[str, str]:
    """
    Load COS configuration from environment variables.

    Returns:
        Dictionary with COS connection parameters

    Raises:
        COSUploadError: If required environment variables are missing
    """
    logger = get_run_logger()

    logger.info("🔑 Loading COS configuration from environment")

    required_vars = [
        'COS_SECRET_ID',
        'COS_SECRET_KEY',
        'COS_BUCKET',
        'COS_REGION'
    ]

    config = {}
    missing_vars = []

    for var in required_vars:
        value = os.getenv(var)
        if not value:
            missing_vars.append(var)
        else:
            config[var] = value

    if missing_vars:
        error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        logger.error(f"❌ {error_msg}")
        raise COSUploadError(error_msg)

    logger.info("✅ COS configuration loaded successfully")
    logger.info(f"  - Bucket: {config['COS_BUCKET']}")
    logger.info(f"  - Region: {config['COS_REGION']}")

    return config


def create_cos_client(config: Dict[str, str]) -> CosS3Client:
    """
    Create Tencent Cloud COS client.

    Note: This is a pure function (not a task) to avoid serialization issues.

    Args:
        config: Dictionary with COS connection parameters

    Returns:
        Configured COS S3 client

    Raises:
        COSUploadError: If client creation fails
    """
    try:
        cos_config = CosConfig(
            Region=config['COS_REGION'],
            SecretId=config['COS_SECRET_ID'],
            SecretKey=config['COS_SECRET_KEY']
        )

        client = CosS3Client(cos_config)
        return client

    except Exception as e:
        error_msg = f"Failed to create COS client: {e}"
        raise COSUploadError(error_msg)


@task(name="Upload Single Audio to COS", retries=2, retry_delay_seconds=1, cache_policy=NONE)
def upload_single_audio_to_cos(
    config: Dict[str, str],
    file_path: str,
    object_key: str
) -> Dict[str, Any]:
    """
    Upload a single audio file to COS.

    Args:
        config: COS configuration dictionary
        file_path: Path to the local audio file
        object_key: Object key for COS (e.g., 'audio/sentences/abc123.mp3')

    Returns:
        Dictionary with upload metadata

    Raises:
        COSUploadError: If upload fails
    """
    logger = get_run_logger()

    file_obj = Path(file_path)

    # Check if file exists
    if not file_obj.exists():
        logger.warning(f"File not found: {file_path}, skipping upload")
        return {
            'success': False,
            'object_key': object_key,
            'error': 'File not found'
        }

    # Create COS client inside the task to avoid serialization issues
    client = create_cos_client(config)
    bucket_name = config['COS_BUCKET']

    try:
        # Upload file to COS
        response = client.upload_file(
            Bucket=bucket_name,
            Key=object_key,
            LocalFilePath=str(file_obj),
            EnableMD5=True
        )

        logger.info(f"✅ Uploaded: {object_key}")

        return {
            'success': True,
            'object_key': object_key,
            'file_name': file_obj.name,
            'file_size': file_obj.stat().st_size,
            'etag': response.get('ETag', '').strip('"')
        }

    except (CosServiceError, CosClientError) as e:
        error_msg = f"COS upload error for {object_key}: {e}"
        logger.error(f"❌ {error_msg}")
        return {
            'success': False,
            'object_key': object_key,
            'error': str(e)
        }
    except Exception as e:
        error_msg = f"Unexpected error uploading {object_key}: {e}"
        logger.error(f"❌ {error_msg}")
        return {
            'success': False,
            'object_key': object_key,
            'error': str(e)
        }


@task(name="Collect Sentence Audio Files", retries=1)
def collect_sentence_audio_files_task(
    sentences_with_audio: List[Dict[str, Any]],
    audio_dir: str
) -> List[Dict[str, str]]:
    """
    Collect sentence audio files for COS upload.

    Args:
        sentences_with_audio: List of sentences with sentence_hash
        audio_dir: Directory containing sentence audio files

    Returns:
        List of dictionaries with file_path and object_key
    """
    logger = get_run_logger()

    audio_dir_path = Path(audio_dir)
    upload_tasks = []

    for sentence in sentences_with_audio:
        sentence_hash = sentence.get('sentence_hash', '').strip()
        if not sentence_hash:
            continue

        audio_filename = f"{sentence_hash}.mp3"
        audio_path = audio_dir_path / audio_filename

        if audio_path.exists():
            # Object key: audio/sentences/{hash}.mp3
            object_key = f"audio/sentences/{audio_filename}"
            upload_tasks.append({
                'file_path': str(audio_path),
                'object_key': object_key
            })

    logger.info(f"📁 Collected {len(upload_tasks)} sentence audio files for upload")
    return upload_tasks


@task(name="Collect Expression Audio Files", retries=1)
def collect_expression_audio_files_task(
    highlight_slugs: List[str],
    audio_dir: str
) -> List[Dict[str, str]]:
    """
    Collect expression audio files for COS upload.

    Args:
        highlight_slugs: List of highlight slugs
        audio_dir: Directory containing expression audio files

    Returns:
        List of dictionaries with file_path and object_key
    """
    logger = get_run_logger()

    audio_dir_path = Path(audio_dir)
    upload_tasks = []

    for slug in highlight_slugs:
        # Convert slug to filename: 'take-out' -> 'take_out.mp3'
        audio_filename = f"{slug.replace('-', '_')}.mp3"
        audio_path = audio_dir_path / audio_filename

        if audio_path.exists():
            # Object key: audio/prefect/expressions/{filename}.mp3
            object_key = f"audio/prefect/expressions/{audio_filename}"
            upload_tasks.append({
                'file_path': str(audio_path),
                'object_key': object_key
            })

    logger.info(f"📁 Collected {len(upload_tasks)} expression audio files for upload")
    return upload_tasks


@task(name="Collect COS Upload Stats", retries=1)
def collect_cos_upload_stats_task(
    upload_results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Collect statistics from COS upload results.

    Args:
        upload_results: List of upload result dictionaries

    Returns:
        Statistics dictionary
    """
    logger = get_run_logger()

    total = len(upload_results)
    successful = sum(1 for r in upload_results if r.get('success', False))
    failed = total - successful
    success_rate = successful / total if total > 0 else 0

    stats = {
        'total_uploads': total,
        'successful_uploads': successful,
        'failed_uploads': failed,
        'success_rate': success_rate
    }

    logger.info(f"📊 COS upload statistics:")
    logger.info(f"  - Total uploads: {stats['total_uploads']}")
    logger.info(f"  - Successful: {stats['successful_uploads']}")
    logger.info(f"  - Failed: {stats['failed_uploads']}")
    logger.info(f"  - Success rate: {stats['success_rate']:.2%}")

    return stats


__all__ = [
    'load_cos_config',
    'upload_single_audio_to_cos',
    'collect_sentence_audio_files_task',
    'collect_expression_audio_files_task',
    'collect_cos_upload_stats_task',
    'COSUploadError'
]
