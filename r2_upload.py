"""
R2 upload tasks for audio files.

Prefect tasks for uploading audio files to Cloudflare R2 Object Storage.
"""

import os
from pathlib import Path
from typing import Any, Dict, List

import boto3
from botocore.exceptions import ClientError, BotoCoreError

from prefect import task, get_run_logger
from prefect.cache_policies import NONE

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class R2UploadError(Exception):
    """Custom exception for R2 upload errors"""
    pass


@task(name="Load R2 Configuration", retries=1)
def load_r2_config() -> Dict[str, str]:
    """
    Load R2 configuration from environment variables.

    Returns:
        Dictionary with R2 connection parameters

    Raises:
        R2UploadError: If required environment variables are missing
    """
    logger = get_run_logger()

    logger.info("🔑 Loading R2 configuration from environment")

    required_vars = [
        'R2_BUCKET_NAME',
        'R2_ACCESS_KEY_ID',
        'R2_SECRET_ACCESS_KEY',
        'R2_ACCOUNT_ID',
        'R2_ENDPOINT_URL'
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
        raise R2UploadError(error_msg)

    logger.info("✅ R2 configuration loaded successfully")
    logger.info(f"  - Bucket: {config['R2_BUCKET_NAME']}")
    logger.info(f"  - Account ID: {config['R2_ACCOUNT_ID']}")
    logger.info(f"  - Endpoint: {config['R2_ENDPOINT_URL']}")

    return config


def create_r2_client(config: Dict[str, str]) -> boto3.client:
    """
    Create boto3 S3 client configured for Cloudflare R2.

    Note: This is a pure function (not a task) to avoid serialization issues.

    Args:
        config: Dictionary with R2 connection parameters

    Returns:
        Configured boto3 S3 client

    Raises:
        R2UploadError: If client creation fails
    """
    try:
        s3_client = boto3.client(
            service_name='s3',
            endpoint_url=config['R2_ENDPOINT_URL'],
            aws_access_key_id=config['R2_ACCESS_KEY_ID'],
            aws_secret_access_key=config['R2_SECRET_ACCESS_KEY'],
            region_name='auto'  # R2 uses 'auto' for automatic region selection
        )

        return s3_client

    except Exception as e:
        error_msg = f"Failed to create R2 client: {e}"
        raise R2UploadError(error_msg)


@task(name="Upload Single Audio to R2", retries=2, retry_delay_seconds=1, cache_policy=NONE)
def upload_single_audio_to_r2(
    config: Dict[str, str],
    file_path: str,
    object_key: str
) -> Dict[str, Any]:
    """
    Upload a single audio file to R2.

    Args:
        config: R2 configuration dictionary
        file_path: Path to the local audio file
        object_key: Object key for R2 (e.g., 'audio/prefect/sentences/abc123.mp3')

    Returns:
        Dictionary with upload metadata
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

    # Create R2 client inside the task to avoid serialization issues
    s3_client = create_r2_client(config)
    bucket_name = config['R2_BUCKET_NAME']

    try:
        # Upload file with appropriate metadata
        extra_args = {
            'ContentType': 'audio/mpeg'  # Set proper MIME type for MP3
        }

        s3_client.upload_file(
            Filename=str(file_obj),
            Bucket=bucket_name,
            Key=object_key,
            ExtraArgs=extra_args
        )

        logger.info(f"✅ Uploaded: {object_key}")

        return {
            'success': True,
            'object_key': object_key,
            'file_name': file_obj.name,
            'file_size': file_obj.stat().st_size,
            'content_type': 'audio/mpeg'
        }

    except (ClientError, BotoCoreError) as e:
        error_msg = f"R2 upload error for {object_key}: {e}"
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


@task(name="Collect R2 Upload Stats", retries=1)
def collect_r2_upload_stats_task(
    upload_results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Collect statistics from R2 upload results.

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

    logger.info(f"📊 R2 upload statistics:")
    logger.info(f"  - Total uploads: {stats['total_uploads']}")
    logger.info(f"  - Successful: {stats['successful_uploads']}")
    logger.info(f"  - Failed: {stats['failed_uploads']}")
    logger.info(f"  - Success rate: {stats['success_rate']:.2%}")

    return stats


@task(name="Upload Episode Media to R2", retries=2, retry_delay_seconds=1, cache_policy=NONE)
def upload_episode_media_to_r2_task(
    config: Dict[str, str],
    mp3_path: str,
    mp4_path: str,
    episode_id: int
) -> Dict[str, Any]:
    """
    Upload episode MP3 and MP4 files to R2.

    Args:
        config: R2 configuration dictionary
        mp3_path: Path to the local MP3 file
        mp4_path: Path to the local MP4 file
        episode_id: Episode ID for file naming

    Returns:
        Dictionary with upload results for both files
    """
    logger = get_run_logger()

    episode_filename = f"EP{episode_id}"
    results = {
        'episode_id': episode_id,
        'mp3_upload': None,
        'mp4_upload': None
    }

    # Upload MP3 to audio/prefect/episodes/
    if mp3_path and Path(mp3_path).exists():
        mp3_object_key = f"audio/prefect/episodes/{episode_filename}.mp3"
        logger.info(f"🎵 Uploading MP3 to R2: {mp3_object_key}")

        mp3_result = upload_single_audio_to_r2(
            config=config,
            file_path=mp3_path,
            object_key=mp3_object_key
        )
        results['mp3_upload'] = mp3_result
    else:
        logger.warning(f"⚠️ MP3 file not found: {mp3_path}, skipping upload")
        results['mp3_upload'] = {'success': False, 'error': 'File not found'}

    # Upload MP4 to videos/prefect/episodes-mp4/
    if mp4_path and Path(mp4_path).exists():
        mp4_object_key = f"videos/prefect/episodes-mp4/{episode_filename}.mp4"
        logger.info(f"🎬 Uploading MP4 to R2: {mp4_object_key}")

        # Create R2 client for video upload
        s3_client = create_r2_client(config)
        bucket_name = config['R2_BUCKET_NAME']
        mp4_file = Path(mp4_path)

        try:
            # Upload video with appropriate metadata
            extra_args = {
                'ContentType': 'video/mp4'  # Set proper MIME type for MP4
            }

            s3_client.upload_file(
                Filename=str(mp4_file),
                Bucket=bucket_name,
                Key=mp4_object_key,
                ExtraArgs=extra_args
            )

            logger.info(f"✅ Uploaded: {mp4_object_key}")

            results['mp4_upload'] = {
                'success': True,
                'object_key': mp4_object_key,
                'file_name': mp4_file.name,
                'file_size': mp4_file.stat().st_size,
                'content_type': 'video/mp4'
            }

        except (ClientError, BotoCoreError) as e:
            error_msg = f"R2 upload error for {mp4_object_key}: {e}"
            logger.error(f"❌ {error_msg}")
            results['mp4_upload'] = {
                'success': False,
                'object_key': mp4_object_key,
                'error': str(e)
            }
        except Exception as e:
            error_msg = f"Unexpected error uploading {mp4_object_key}: {e}"
            logger.error(f"❌ {error_msg}")
            results['mp4_upload'] = {
                'success': False,
                'object_key': mp4_object_key,
                'error': str(e)
            }
    else:
        logger.warning(f"⚠️ MP4 file not found: {mp4_path}, skipping upload")
        results['mp4_upload'] = {'success': False, 'error': 'File not found'}

    # Summary
    mp3_success = results['mp3_upload'].get('success', False)
    mp4_success = results['mp4_upload'].get('success', False)

    if mp3_success and mp4_success:
        logger.info(f"🎉 Successfully uploaded both MP3 and MP4 for episode {episode_id}")
    elif mp3_success or mp4_success:
        logger.warning(f"⚠️ Partial upload success for episode {episode_id}")
    else:
        logger.error(f"❌ Failed to upload MP3 and MP4 for episode {episode_id}")

    return results


__all__ = [
    'load_r2_config',
    'upload_single_audio_to_r2',
    'collect_r2_upload_stats_task',
    'upload_episode_media_to_r2_task',
    'R2UploadError'
]
