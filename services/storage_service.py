"""
Async cloud storage service for audio files.

Provides async upload functionality for Cloudflare R2 and Tencent Cloud COS.
Uses aioboto3 for R2 and thread pool for COS (which doesn't have async client).
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class StorageUploadError(Exception):
    """Custom exception for storage upload errors."""
    pass


async def upload_to_r2_async(
    file_path: str,
    object_key: str,
    bucket_name: str,
    access_key_id: str,
    secret_access_key: str,
    endpoint_url: str,
    content_type: str = 'audio/mpeg'
) -> Dict[str, Any]:
    """
    Upload file to Cloudflare R2 asynchronously.

    Args:
        file_path: Local file path to upload
        object_key: S3 object key (path in bucket)
        bucket_name: R2 bucket name
        access_key_id: R2 access key ID
        secret_access_key: R2 secret access key
        endpoint_url: R2 endpoint URL
        content_type: Content type (default: audio/mpeg)

    Returns:
        Dict with upload result

    Examples:
        >>> import asyncio
        >>> result = asyncio.run(upload_to_r2_async(
        ...     "/tmp/test.mp3",
        ...     "audio/test.mp3",
        ...     "my-bucket",
        ...     "access-key",
        ...     "secret-key",
        ...     "https://endpoint.r2.cloudflarestorage.com"
        ... ))
        >>> result['success']
        True
    """
    try:
        import aioboto3

        file_obj = Path(file_path)
        if not file_obj.exists():
            return {
                'success': False,
                'object_key': object_key,
                'error': 'File not found'
            }

        session = aioboto3.Session()
        async with session.client(
            service_name='s3',
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name='auto'
        ) as s3_client:
            # Upload file
            extra_args = {'ContentType': content_type}
            await s3_client.upload_file(
                Filename=str(file_obj),
                Bucket=bucket_name,
                Key=object_key,
                ExtraArgs=extra_args
            )

            return {
                'success': True,
                'object_key': object_key,
                'file_name': file_obj.name,
                'file_size': file_obj.stat().st_size,
                'content_type': content_type
            }

    except ImportError:
        return {
            'success': False,
            'object_key': object_key,
            'error': 'aioboto3 not installed'
        }
    except Exception as e:
        logger.error(f"R2 upload failed for {object_key}: {e}")
        return {
            'success': False,
            'object_key': object_key,
            'error': str(e)
        }


def upload_to_cos_sync(
    file_path: str,
    object_key: str,
    bucket: str,
    region: str,
    secret_id: str,
    secret_key: str
) -> Dict[str, Any]:
    """
    Upload file to Tencent Cloud COS synchronously.

    This is a sync function because cos-python-sdk-v5 doesn't have async support.
    It will be run in a thread pool from async code.

    Args:
        file_path: Local file path to upload
        object_key: COS object key
        bucket: COS bucket name
        region: COS region
        secret_id: COS secret ID
        secret_key: COS secret key

    Returns:
        Dict with upload result
    """
    try:
        from qcloud_cos import CosConfig, CosS3Client

        cos_config = CosConfig(
            Region=region,
            SecretId=secret_id,
            SecretKey=secret_key
        )
        client = CosS3Client(cos_config)

        file_obj = Path(file_path)
        if not file_obj.exists():
            return {
                'success': False,
                'object_key': object_key,
                'error': 'File not found'
            }

        response = client.upload_file(
            Bucket=bucket,
            Key=object_key,
            LocalFilePath=str(file_obj),
            EnableMD5=True
        )

        return {
            'success': True,
            'object_key': object_key,
            'file_name': file_obj.name,
            'file_size': file_obj.stat().st_size,
            'etag': response.get('ETag', '').strip('"')
        }

    except ImportError:
        return {
            'success': False,
            'object_key': object_key,
            'error': 'qcloud_cos not installed'
        }
    except Exception as e:
        logger.error(f"COS upload failed for {object_key}: {e}")
        return {
            'success': False,
            'object_key': object_key,
            'error': str(e)
        }


async def batch_upload_r2(
    upload_files: List[Dict[str, str]],
    max_concurrent: int = 10
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Upload multiple files to R2 concurrently.

    Args:
        upload_files: List of dicts with 'file_path', 'object_key', 'sentence_hash'
        max_concurrent: Maximum concurrent uploads (default: 10)

    Returns:
        Tuple of (results list, statistics dict)
    """
    # Load R2 configuration
    r2_config = {
        'R2_BUCKET_NAME': os.getenv('R2_BUCKET_NAME'),
        'R2_ACCESS_KEY_ID': os.getenv('R2_ACCESS_KEY_ID'),
        'R2_SECRET_ACCESS_KEY': os.getenv('R2_SECRET_ACCESS_KEY'),
        'R2_ENDPOINT_URL': os.getenv('R2_ENDPOINT_URL')
    }

    # Check if R2 is configured
    if not all(r2_config.values()):
        logger.warning("R2 configuration incomplete - skipping upload")
        return [], {
            'error': 'R2 configuration incomplete - missing environment variables',
            'total_uploads': 0,
            'successful_uploads': 0,
            'failed_uploads': 0,
            'success_rate': 0.0
        }

    if not upload_files:
        logger.info("No files to upload to R2")
        return [], {
            'total_uploads': 0,
            'successful_uploads': 0,
            'failed_uploads': 0,
            'success_rate': 0.0
        }

    logger.info(f"🔑 R2 configuration loaded, starting upload of {len(upload_files)} files...")

    try:
        import aioboto3
        from botocore.config import Config

        # Configure boto with increased timeouts and connection pool settings
        boto_config = Config(
            connect_timeout=30,
            read_timeout=60,
            retries={'max_attempts': 2, 'mode': 'standard'},
            max_pool_connections=max_concurrent + 5
        )

        # Create shared session and client for all uploads
        session = aioboto3.Session()
        async with session.client(
            service_name='s3',
            endpoint_url=r2_config['R2_ENDPOINT_URL'],
            aws_access_key_id=r2_config['R2_ACCESS_KEY_ID'],
            aws_secret_access_key=r2_config['R2_SECRET_ACCESS_KEY'],
            region_name='auto',
            config=boto_config
        ) as s3_client:

            # Create semaphore for concurrency control
            semaphore = asyncio.Semaphore(max_concurrent)

            async def upload_single_file(file_info: Dict[str, str]) -> Dict[str, Any]:
                """Upload single file using shared client."""
                async with semaphore:
                    try:
                        file_path = file_info['file_path']
                        object_key = file_info['object_key']

                        file_obj = Path(file_path)
                        if not file_obj.exists():
                            return {
                                'success': False,
                                'object_key': object_key,
                                'error': 'File not found'
                            }

                        # Upload using shared client
                        await s3_client.upload_file(
                            Filename=str(file_obj),
                            Bucket=r2_config['R2_BUCKET_NAME'],
                            Key=object_key,
                            ExtraArgs={'ContentType': 'audio/mpeg'}
                        )

                        return {
                            'success': True,
                            'object_key': object_key,
                            'file_name': file_obj.name,
                            'file_size': file_obj.stat().st_size,
                            'content_type': 'audio/mpeg'
                        }

                    except Exception as e:
                        logger.error(f"R2 upload failed for {object_key}: {e}")
                        return {
                            'success': False,
                            'object_key': object_key,
                            'error': str(e)
                        }

            # Upload all files concurrently
            tasks = [upload_single_file(file_info) for file_info in upload_files]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Handle exceptions
            processed_results = []
            for idx, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"R2 upload exception for file {idx}: {result}")
                    processed_results.append({
                        'success': False,
                        'object_key': upload_files[idx].get('object_key', 'unknown'),
                        'error': str(result)
                    })
                else:
                    processed_results.append(result)

            # Wait for graceful connection cleanup
            await asyncio.sleep(2.0)  # 增加到2秒，确保连接完全关闭

        # Calculate statistics (outside the client context)
        total = len(processed_results)
        successful = sum(1 for r in processed_results if r.get('success', False))
        stats = {
            'total_uploads': total,
            'successful_uploads': successful,
            'failed_uploads': total - successful,
            'success_rate': successful / total if total > 0 else 0.0
        }

        logger.info(f"📊 R2 upload: {successful}/{total} successful")
        return processed_results, stats

    except ImportError:
        logger.error("aioboto3 not installed")
        return [], {
            'error': 'aioboto3 not installed',
            'total_uploads': 0,
            'successful_uploads': 0,
            'failed_uploads': 0,
            'success_rate': 0.0
        }
    except Exception as e:
        logger.error(f"R2 batch upload failed: {e}")
        return [], {
            'error': str(e),
            'total_uploads': 0,
            'successful_uploads': 0,
            'failed_uploads': 0,
            'success_rate': 0.0
        }


async def batch_upload_cos(
    upload_files: List[Dict[str, str]],
    max_workers: int = 4
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Upload multiple files to COS using thread pool (since COS SDK is sync).

    Args:
        upload_files: List of dicts with 'file_path', 'object_key', 'sentence_hash'
        max_workers: Maximum thread pool workers (default: 4)

    Returns:
        Tuple of (results list, statistics dict)
    """
    # Load COS configuration
    cos_config = {
        'COS_SECRET_ID': os.getenv('COS_SECRET_ID'),
        'COS_SECRET_KEY': os.getenv('COS_SECRET_KEY'),
        'COS_BUCKET': os.getenv('COS_BUCKET'),
        'COS_REGION': os.getenv('COS_REGION')
    }

    # Check if COS is configured
    if not all(cos_config.values()):
        logger.warning("COS configuration incomplete - skipping upload")
        return [], {
            'error': 'COS configuration incomplete - missing environment variables',
            'total_uploads': 0,
            'successful_uploads': 0,
            'failed_uploads': 0,
            'success_rate': 0.0
        }

    if not upload_files:
        logger.info("No files to upload to COS")
        return [], {
            'total_uploads': 0,
            'successful_uploads': 0,
            'failed_uploads': 0,
            'success_rate': 0.0
        }

    logger.info(f"🔑 COS configuration loaded, starting upload of {len(upload_files)} files...")

    # Run sync uploads in thread pool
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            loop.run_in_executor(
                executor,
                upload_to_cos_sync,
                file_info['file_path'],
                file_info['object_key'],
                cos_config['COS_BUCKET'],
                cos_config['COS_REGION'],
                cos_config['COS_SECRET_ID'],
                cos_config['COS_SECRET_KEY']
            )
            for file_info in upload_files
        ]
        results = await asyncio.gather(*futures, return_exceptions=True)

    # Handle exceptions
    processed_results = []
    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"COS upload exception for file {idx}: {result}")
            processed_results.append({
                'success': False,
                'object_key': upload_files[idx].get('object_key', 'unknown'),
                'error': str(result)
            })
        else:
            processed_results.append(result)

    # Calculate statistics
    total = len(processed_results)
    successful = sum(1 for r in processed_results if r.get('success', False))
    stats = {
        'total_uploads': total,
        'successful_uploads': successful,
        'failed_uploads': total - successful,
        'success_rate': successful / total if total > 0 else 0.0
    }

    logger.info(f"📊 COS upload: {successful}/{total} successful")
    return processed_results, stats


async def upload_audio_files(
    upload_files: List[Dict[str, str]],
    upload_to_cos: bool = True,
    upload_to_r2: bool = True,
    max_concurrent_r2: int = 10,
    max_workers_cos: int = 4,
    r2_files: Optional[List[Dict[str, str]]] = None,
    cos_files: Optional[List[Dict[str, str]]] = None
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
    """
    Upload audio files to both COS and R2 concurrently.

    Args:
        upload_files: List of dicts with 'file_path', 'object_key', 'sentence_hash'
        upload_to_cos: Whether to upload to COS (default: True)
        upload_to_r2: Whether to upload to R2 (default: True)
        max_concurrent_r2: Max concurrent R2 uploads (default: 10)
        max_workers_cos: Max thread pool workers for COS (default: 4)
        r2_files: Optional specific list for R2 upload (default: None, uses upload_files)
        cos_files: Optional specific list for COS upload (default: None, uses upload_files)

    Returns:
        Tuple of (cos_results, r2_results, cos_stats, r2_stats)
    """
    tasks = []

    # Upload to COS and R2 in parallel
    # Use specific file lists if provided, otherwise use upload_files
    if upload_to_cos:
        cos_upload_list = cos_files if cos_files is not None else upload_files
        tasks.append(batch_upload_cos(cos_upload_list, max_workers_cos))
    else:
        tasks.append(asyncio.sleep(0))  # Placeholder

    if upload_to_r2:
        r2_upload_list = r2_files if r2_files is not None else upload_files
        tasks.append(batch_upload_r2(r2_upload_list, max_concurrent_r2))
    else:
        tasks.append(asyncio.sleep(0))  # Placeholder

    # Execute both uploads concurrently
    results = await asyncio.gather(*tasks)

    # Extract results
    if upload_to_cos:
        cos_results, cos_stats = results[0]
    else:
        cos_results, cos_stats = [], {'total_uploads': 0, 'successful_uploads': 0, 'failed_uploads': 0, 'success_rate': 0.0}

    if upload_to_r2:
        r2_results, r2_stats = results[1]
    else:
        r2_results, r2_stats = [], {'total_uploads': 0, 'successful_uploads': 0, 'failed_uploads': 0, 'success_rate': 0.0}

    return cos_results, r2_results, cos_stats, r2_stats


__all__ = [
    'upload_to_r2_async',
    'upload_to_cos_sync',
    'batch_upload_r2',
    'batch_upload_cos',
    'upload_audio_files',
    'StorageUploadError'
]
